# Email Thread Deduplication Queues D1

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Inbound email forwarding and retry loops cause the same message to arrive multiple times via Cloudflare Email Routing Workers, creating duplicate tickets, duplicate webhook calls, or duplicate D1 rows in your inbound-processing pipeline.

## Context
Cloudflare Queues provides at-least-once delivery guarantees — a message may be delivered more than once if the consumer fails to acknowledge it. Combined with SMTP's own retry semantics (a sending MTA may redeliver if it does not receive a 250 OK fast enough), deduplication must be applied at the application layer. A D1 table keyed on the RFC 5321 `Message-ID` header acts as a durable deduplication ledger; a KV namespace caches the most recent 24 hours of seen IDs for a fast O(1) path before touching D1.

## Architecture

```
Email Routing Worker  →  Queue ("inbound-email-raw")
                              ↓
                        Queue Consumer Worker
                              ↓  read Message-ID
                        KV dedup cache (24 h TTL)
                              ↓ miss
                        D1 dedup_log table (upsert, RETURNING changed)
                              ↓ new message
                        D1 email_threads / email_messages
                              ↓
                        Downstream Queue ("inbound-email-processed")
```

## D1 Schema

```sql
-- Deduplication ledger (keyed on RFC 5321 Message-ID)
CREATE TABLE dedup_log (
  message_id      TEXT PRIMARY KEY,
  received_at     TEXT NOT NULL DEFAULT (datetime('now')),
  queue_message_id TEXT,                -- Cloudflare Queue message ID for audit
  disposition     TEXT NOT NULL DEFAULT 'processed'  -- 'processed' | 'duplicate'
);

-- Thread resolution table
CREATE TABLE email_threads (
  thread_id   TEXT PRIMARY KEY,          -- stable ID derived from References / In-Reply-To chain
  subject     TEXT NOT NULL,
  initiator   TEXT NOT NULL,             -- Message-ID of the first message in the chain
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE email_messages (
  id          TEXT PRIMARY KEY,          -- Message-ID (normalised)
  thread_id   TEXT NOT NULL REFERENCES email_threads(thread_id),
  from_addr   TEXT NOT NULL,
  to_addr     TEXT NOT NULL,
  subject     TEXT NOT NULL,
  in_reply_to TEXT,
  refs        TEXT,                      -- space-separated References list
  received_at TEXT NOT NULL DEFAULT (datetime('now')),
  raw_key     TEXT                       -- R2 key for the raw MIME blob
);

CREATE INDEX idx_em_thread ON email_messages(thread_id);
CREATE INDEX idx_em_in_reply_to ON email_messages(in_reply_to);
```

## Email Routing Worker (Producer)

```typescript
// routing-worker.ts
import { EmailMessage } from 'cloudflare:email';

export interface Env {
  INBOUND_QUEUE: Queue;
}

export default {
  async email(message: EmailMessage, env: Env): Promise<void> {
    // Enqueue raw headers + metadata; do NOT buffer the full MIME body here
    // (EmailMessage.raw is a ReadableStream — pass key metadata only)
    const headers: Record<string, string> = {};
    for (const [k, v] of message.headers) {
      headers[k.toLowerCase()] = v;
    }

    await env.INBOUND_QUEUE.send({
      messageId: headers['message-id'] ?? `<generated-${crypto.randomUUID()}@noid>`,
      inReplyTo: headers['in-reply-to'] ?? null,
      references: headers['references'] ?? null,
      from: message.from,
      to: message.to,
      subject: headers['subject'] ?? '(no subject)',
      receivedAt: new Date().toISOString(),
    });

    message.forward('archive@yourdomain.com'); // keep a copy
  },
};
```

## Queue Consumer Worker (Deduplication + Threading)

```typescript
// consumer-worker.ts
import { Env, InboundPayload } from './types';

export interface InboundPayload {
  messageId: string;
  inReplyTo: string | null;
  references: string | null;
  from: string;
  to: string;
  subject: string;
  receivedAt: string;
}

export interface Env {
  DB: D1Database;
  DEDUP_CACHE: KVNamespace;
  PROCESSED_QUEUE: Queue;
}

export default {
  async queue(batch: MessageBatch<InboundPayload>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processMessage(msg.body, msg.id, env);
        msg.ack();
      } catch (err) {
        console.error('Failed to process message', msg.body.messageId, err);
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function processMessage(
  payload: InboundPayload,
  queueMsgId: string,
  env: Env
): Promise<void> {
  const normalised = normaliseMessageId(payload.messageId);

  // 1. Fast KV dedup check
  const cacheKey = `dedup:${normalised}`;
  const cached = await env.DEDUP_CACHE.get(cacheKey);
  if (cached) {
    console.log(`Duplicate (KV): ${normalised}`);
    return; // already processed
  }

  // 2. Durable D1 dedup upsert — RETURNING lets us detect first vs duplicate
  const result = await env.DB.prepare(
    `INSERT INTO dedup_log (message_id, queue_message_id)
     VALUES (?, ?)
     ON CONFLICT (message_id) DO UPDATE
       SET disposition = 'duplicate'
     RETURNING disposition`
  ).bind(normalised, queueMsgId).first<{ disposition: string }>();

  const isNew = result?.disposition === 'processed';

  // Prime KV cache regardless — even duplicates should short-circuit next time
  await env.DEDUP_CACHE.put(cacheKey, isNew ? 'processed' : 'duplicate', {
    expirationTtl: 60 * 60 * 24, // 24 h
  });

  if (!isNew) {
    console.log(`Duplicate (D1): ${normalised}`);
    return;
  }

  // 3. Resolve or create thread
  const threadId = await resolveThread(payload, env);

  // 4. Insert message row
  await env.DB.prepare(
    `INSERT OR IGNORE INTO email_messages
       (id, thread_id, from_addr, to_addr, subject, in_reply_to, refs, received_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    normalised,
    threadId,
    payload.from,
    payload.to,
    payload.subject,
    payload.inReplyTo ? normaliseMessageId(payload.inReplyTo) : null,
    payload.references,
    payload.receivedAt
  ).run();

  // 5. Forward to downstream processing queue
  await env.PROCESSED_QUEUE.send({ ...payload, messageId: normalised, threadId });
}

async function resolveThread(payload: InboundPayload, env: Env): Promise<string> {
  const replyTo = payload.inReplyTo ? normaliseMessageId(payload.inReplyTo) : null;

  if (replyTo) {
    // Look up the parent message's thread
    const parent = await env.DB.prepare(
      `SELECT thread_id FROM email_messages WHERE id = ?`
    ).bind(replyTo).first<{ thread_id: string }>();

    if (parent) {
      // Update thread's updated_at
      await env.DB.prepare(
        `UPDATE email_threads SET updated_at = ? WHERE thread_id = ?`
      ).bind(payload.receivedAt, parent.thread_id).run();
      return parent.thread_id;
    }
  }

  // No parent found — start a new thread
  const threadId = `th_${crypto.randomUUID().replace(/-/g, '').slice(0, 16)}`;
  await env.DB.prepare(
    `INSERT INTO email_threads (thread_id, subject, initiator)
     VALUES (?, ?, ?)`
  ).bind(threadId, cleanSubject(payload.subject), normaliseMessageId(payload.messageId)).run();

  return threadId;
}

function normaliseMessageId(raw: string): string {
  // Strip surrounding angle brackets and whitespace
  return raw.trim().replace(/^<|>$/g, '').toLowerCase();
}

function cleanSubject(subject: string): string {
  // Strip Re: / Fwd: prefixes for thread subject normalisation
  return subject.replace(/^(re|fwd?|fw):\s*/i, '').trim();
}
```

## Querying Threads

```typescript
// query.ts
export async function getThread(
  threadId: string,
  env: { DB: D1Database }
): Promise<{ thread: unknown; messages: unknown[] }> {
  const [thread, messages] = await Promise.all([
    env.DB.prepare(`SELECT * FROM email_threads WHERE thread_id = ?`)
      .bind(threadId).first(),
    env.DB.prepare(
      `SELECT * FROM email_messages WHERE thread_id = ? ORDER BY received_at ASC`
    ).bind(threadId).all(),
  ]);
  return { thread, messages: messages.results };
}
```

## Anti-patterns
- Using only KV for deduplication — KV is eventually consistent; two concurrent Queue consumers can both miss the key and both process the same message; D1 with a unique constraint is the authoritative gate.
- Keying on the `Subject` header instead of `Message-ID` — subjects are not unique across senders, conversation reconstructions will merge unrelated threads.
- Calling `msg.ack()` before the D1 write completes — if D1 throws after the ack, the message is lost; always ack after successful persistence.
- Storing the full raw MIME body in D1 — D1 row size is capped at 1 MB; stream large bodies to R2 and store only the R2 key in D1.
- Using `References` header alone for thread linking without fallback to `In-Reply-To` — many MUAs omit one or the other; check both before creating a new thread.

## Gotchas
- `EmailMessage.raw` in Email Routing Workers is a one-time-read `ReadableStream`; it cannot be teed and passed into the Queue body simultaneously — pass only header metadata through the Queue and retrieve the full body from R2 or a separate archive path.
- Queue batch size defaults to 10; if a spam burst delivers 100 duplicates, 10 consumers fire in parallel and all hit the D1 upsert simultaneously — the `ON CONFLICT DO UPDATE` handles this correctly, but watch D1 write latency under load.
- The `Message-ID` generated by some mail servers contains uppercase characters; always `toLowerCase()` before storing or comparing.
- `RETURNING` on `INSERT ... ON CONFLICT DO UPDATE` returns the _new_ values after the update, not the original inserted row — use `disposition = 'processed'` as the sentinel for a first-time insert, which is the default column value.
- D1 `INSERT OR IGNORE` silently discards duplicate inserts into `email_messages` without error; log the row count from `result.meta.changes` to detect silent no-ops during debugging.

## Verification
1. Send the same email twice (same `Message-ID`) within 5 seconds; confirm only one row appears in `email_messages`.
2. Check `dedup_log` — the second row should show `disposition = 'duplicate'`.
3. Send a reply with matching `In-Reply-To`; confirm both messages share the same `thread_id` in `email_messages`.
4. Send a fresh message with no `In-Reply-To`; confirm a new `email_threads` row is created.
5. Inspect KV namespace and confirm `dedup:{message-id}` keys exist with a 24-hour TTL.

## Related
- `workers-email-reply-parsing-thread-detection.md`
- `inbound-webhook-workers-d1.md`
- `transactional-queue-cloudflare-queues.md`
- `email-webhook-idempotency-deduplication.md`
- `email-conversation-threading-d1-workers.md`

## Sources
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/email-routing/email-workers/
- https://datatracker.ietf.org/doc/html/rfc5321#section-4.4
