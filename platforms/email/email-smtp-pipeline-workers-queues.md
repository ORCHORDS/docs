# SMTP Processing Pipeline with Workers and Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Inbound emails need to be parsed, have attachments archived, and emit structured events for downstream consumers — all asynchronously without blocking delivery acknowledgment. A synchronous Email Worker cannot reliably complete multi-step processing within its execution budget.

## Context

The Email Worker buffers the raw message as an ArrayBuffer, publishes it to a primary Queue, and immediately forwards to an internal address. A Queue consumer (the pipeline worker) parses the MIME payload using PostalMime, stores message metadata in D1 `smtp_pipeline_log`, archives attachments to R2, then publishes a processed event to a secondary Queue for downstream consumers such as CRM integrations or ticketing systems.

Requirements:
- Email Worker (ingest)
- Queue consumer Worker (pipeline)
- D1 database bound as `DB`
- R2 bucket bound as `ATTACHMENTS`
- Primary Queue `RAW_EMAIL_QUEUE` and secondary Queue `PROCESSED_EMAIL_QUEUE`
- `postal-mime` npm package

## D1 Schema

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS smtp_pipeline_log (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id      TEXT    NOT NULL,
  from_addr       TEXT    NOT NULL,
  to_addr         TEXT    NOT NULL,
  subject         TEXT,
  plain_text      TEXT,
  attachment_keys TEXT,   -- JSON array of R2 object keys
  received_at     TEXT    NOT NULL DEFAULT (datetime('now')),
  status          TEXT    NOT NULL DEFAULT 'received'
);
CREATE INDEX IF NOT EXISTS idx_pipeline_msgid ON smtp_pipeline_log(message_id);
```

## Email Worker — Ingest and Enqueue

```typescript
import type { EmailMessage } from 'cloudflare:email';

export interface IngestEnv {
  RAW_EMAIL_QUEUE: Queue;
}

export default {
  async email(message: EmailMessage, env: IngestEnv): Promise<void> {
    // Buffer the full raw message before any forwarding
    const rawBuffer = await new Response(message.raw).arrayBuffer();
    const rawBase64 = bufferToBase64(rawBuffer);

    await env.RAW_EMAIL_QUEUE.send({
      messageId: message.headers.get('Message-ID') ?? `${Date.now()}`,
      fromAddr: message.from,
      toAddr: message.to,
      rawBase64,
    });

    // Forward to internal mailbox for archival backup
    await message.forward('archive@internal.yourdomain.com');
  },
};

function bufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}
```

## Queue Consumer — MIME Parse, D1, R2, and Downstream Queue

```typescript
import PostalMime from 'postal-mime';

export interface PipelineEnv {
  DB: D1Database;
  ATTACHMENTS: R2Bucket;
  PROCESSED_EMAIL_QUEUE: Queue;
}

interface RawEmailPayload {
  messageId: string;
  fromAddr: string;
  toAddr: string;
  rawBase64: string;
}

export default {
  async queue(batch: MessageBatch<RawEmailPayload>, env: PipelineEnv): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processEmail(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error(`[pipeline] Failed to process ${msg.body.messageId}:`, err);
        msg.retry();
      }
    }
  },
};

async function processEmail(payload: RawEmailPayload, env: PipelineEnv): Promise<void> {
  const rawBytes = base64ToBuffer(payload.rawBase64);
  const parsed = await new PostalMime().parse(rawBytes);

  const attachmentKeys: string[] = [];

  for (const attachment of parsed.attachments ?? []) {
    const key = `${payload.messageId}/${attachment.filename ?? `attachment-${Date.now()}`}`;
    await env.ATTACHMENTS.put(key, attachment.content, {
      httpMetadata: { contentType: attachment.mimeType },
    });
    attachmentKeys.push(key);
  }

  await env.DB.prepare(
    `INSERT INTO smtp_pipeline_log
       (message_id, from_addr, to_addr, subject, plain_text, attachment_keys, status)
     VALUES (?, ?, ?, ?, ?, ?, 'processed')`
  ).bind(
    payload.messageId,
    payload.fromAddr,
    payload.toAddr,
    parsed.subject ?? null,
    parsed.text ?? null,
    JSON.stringify(attachmentKeys),
  ).run();

  await env.PROCESSED_EMAIL_QUEUE.send({
    messageId: payload.messageId,
    fromAddr: payload.fromAddr,
    subject: parsed.subject,
    attachmentCount: attachmentKeys.length,
  });
}

function base64ToBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}
```

## wrangler.toml Configuration

```toml
name = "smtp-pipeline"
main = "src/pipeline.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "pipeline-db"
database_id = "<your-d1-id>"

[[r2_buckets]]
binding = "ATTACHMENTS"
bucket_name = "email-attachments"

[[queues.consumers]]
queue = "raw-email-queue"
max_batch_size = 10
max_batch_timeout = 30

[[queues.producers]]
binding = "PROCESSED_EMAIL_QUEUE"
queue = "processed-email-queue"
```

## Anti-patterns

- Do not call `PostalMime.parse()` inside the Email Worker; the synchronous email event has a tight CPU budget.
- Do not store full raw email bodies in D1; D1 rows have a 1 MB limit and emails can be larger. Use R2 for raw storage.
- Do not `ackAll()` on the batch if individual messages can fail independently; use per-message `ack()`/`retry()`.
- Do not let attachment keys grow unbounded in D1; implement a cleanup job that deletes R2 objects and D1 rows after retention period.

## Gotchas

- `message.raw` is a `ReadableStream`; it can only be consumed once. Buffer it before any branching logic.
- Base64-encoding the raw buffer for Queue transport increases payload size by ~33%; ensure messages stay under the 128 KB Queue message limit.
- `PostalMime` must be installed as an npm dependency: `npm install postal-mime`.
- R2 `put()` does not create directories; object keys with `/` are valid and served as a flat namespace.

## Verification

```bash
# Confirm D1 log entries after a test email
wrangler d1 execute pipeline-db \
  --command "SELECT message_id, subject, attachment_keys, status FROM smtp_pipeline_log LIMIT 5;"

# List R2 attachment objects
wrangler r2 object list email-attachments

# Monitor pipeline consumer logs
wrangler tail smtp-pipeline --format pretty
```

## Related

- `email-digest-batching-queues-d1-workers.md`
- `email-forwarding-loop-detection-d1-workers.md`
- [postal-mime npm package](https://www.npmjs.com/package/postal-mime)
- [Cloudflare R2 docs](https://developers.cloudflare.com/r2/)

## Sources

- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/r2/
- https://www.npmjs.com/package/postal-mime
