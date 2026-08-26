# Inbound Email Fanout to Cloudflare Queues with Email Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Email Routing Worker receives inbound email and needs to do several things with each message:

- Archive the raw MIME to R2 for compliance retention
- Send a Slack notification summarising the sender and subject
- Run a Workers AI classification to tag the message category
- Write a search index record to D1

Doing all of this synchronously inside the `email()` handler is impractical because:

1. The handler has a 30-second CPU time limit and a similar wall-clock limit
2. One failing step (e.g. a Slack webhook timeout) rolls back all others
3. Each step has different retry, latency, and ordering requirements

The solution is to publish the message payload to one or more Cloudflare Queues inside the email handler and let Queue Consumers handle each processing step asynchronously, independently, and with automatic retries.

---

## Context

Cloudflare Queues connects a **Producer** (the email Worker, calling `env.QUEUE.send()`) to one or more **Consumers** (`queue` handler exported from a Worker). Each Queue has exactly one Consumer Worker, but a single email Worker can publish to multiple Queues in parallel.

The `email()` handler must read `message.raw` into a buffer before the handler returns because the stream is closed at the end of the invocation. The buffer is serialised to a Base64 string and included in the queue message payload. Queue message size is capped at 128 KB; messages larger than this should be staged to R2 first with only the R2 key in the queue payload.

---

## wrangler.toml Configuration

```toml
name = "email-fanout"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[email]]
type = "email"
name = "EMAIL"

[[queues.producers]]
binding = "ARCHIVE_QUEUE"
queue   = "email-archive"

[[queues.producers]]
binding = "NOTIFY_QUEUE"
queue   = "email-notify"

[[queues.producers]]
binding = "CLASSIFY_QUEUE"
queue   = "email-classify"

[[r2_buckets]]
binding  = "ARCHIVE_BUCKET"
bucket_name = "email-archive"

[[d1_databases]]
binding       = "INDEX_DB"
database_name = "email-index"
database_id   = "<d1-database-id>"

[vars]
MAX_INLINE_BYTES = "65536"   # 64 KB; stage larger messages to R2
```

---

## Email Handler: Fanout Producer

```typescript
import type { EmailMessage } from "cloudflare:email";

interface Env {
  ARCHIVE_QUEUE: Queue;
  NOTIFY_QUEUE: Queue;
  CLASSIFY_QUEUE: Queue;
  ARCHIVE_BUCKET: R2Bucket;
  INDEX_DB: D1Database;
  MAX_INLINE_BYTES: string;
}

export interface EmailPayload {
  messageId: string;
  from: string;
  to: string;
  subject: string;
  receivedAt: string;
  rawBase64?: string;
  r2Key?: string;
}

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    const receivedAt = new Date().toISOString();
    const messageId = message.headers.get("Message-ID") ?? `<${crypto.randomUUID()}@unknown>`;
    const subject = message.headers.get("Subject") ?? "(no subject)";

    // Buffer the full message — the stream closes when the handler returns
    const rawBuffer = await new Response(message.raw).arrayBuffer();
    const rawBytes = new Uint8Array(rawBuffer);
    const maxInline = parseInt(env.MAX_INLINE_BYTES, 10);

    let payload: EmailPayload;

    if (rawBytes.byteLength <= maxInline) {
      payload = {
        messageId,
        from: message.from,
        to: message.to,
        subject,
        receivedAt,
        rawBase64: btoa(String.fromCharCode(...rawBytes)),
      };
    } else {
      const r2Key = `staged/${receivedAt.slice(0, 10)}/${messageId.replace(/[<>]/g, "")}.eml`;
      await env.ARCHIVE_BUCKET.put(r2Key, rawBuffer);
      payload = {
        messageId,
        from: message.from,
        to: message.to,
        subject,
        receivedAt,
        r2Key,
      };
    }

    // Publish to all queues in parallel; failures are isolated per queue
    await Promise.allSettled([
      env.ARCHIVE_QUEUE.send(payload),
      env.NOTIFY_QUEUE.send({ messageId, from: payload.from, subject, receivedAt }),
      env.CLASSIFY_QUEUE.send({ messageId, from: payload.from, subject, receivedAt }),
    ]);

    await message.forward("inbox@team.yourdomain.com");
  },
};
```

---

## Archive Consumer: Write Raw EML to R2

```typescript
// src/archive-consumer.ts
interface Env {
  ARCHIVE_BUCKET: R2Bucket;
}

export default {
  async queue(batch: MessageBatch<EmailPayload>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { messageId, receivedAt, rawBase64, r2Key } = msg.body;

      if (r2Key) {
        const finalKey = `archive/${receivedAt.slice(0, 7)}/${messageId.replace(/[<>]/g, "")}.eml`;
        const obj = await env.ARCHIVE_BUCKET.get(r2Key);
        if (obj) {
          await env.ARCHIVE_BUCKET.put(finalKey, obj.body, {
            httpMetadata: { contentType: "message/rfc822" },
          });
          await env.ARCHIVE_BUCKET.delete(r2Key);
        }
        msg.ack();
        continue;
      }

      if (!rawBase64) { msg.ack(); continue; }

      const rawBytes = Uint8Array.from(atob(rawBase64), (c) => c.charCodeAt(0));
      const archiveKey = `archive/${receivedAt.slice(0, 7)}/${messageId.replace(/[<>]/g, "")}.eml`;

      await env.ARCHIVE_BUCKET.put(archiveKey, rawBytes, {
        httpMetadata: { contentType: "message/rfc822" },
        customMetadata: { originalMessageId: messageId },
      });

      msg.ack();
    }
  },
};
```

---

## Notification Consumer: Post to Slack

```typescript
// src/notify-consumer.ts
interface Env {
  SLACK_WEBHOOK_URL: string;
}

export default {
  async queue(batch: MessageBatch<{ messageId: string; from: string; subject: string; receivedAt: string }>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { from, subject, receivedAt } = msg.body;

      const resp = await fetch(env.SLACK_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `New inbound email`,
          blocks: [
            {
              type: "section",
              fields: [
                { type: "mrkdwn", text: `*From:* ${from}` },
                { type: "mrkdwn", text: `*Subject:* ${subject}` },
                { type: "mrkdwn", text: `*Received:* ${receivedAt}` },
              ],
            },
          ],
        }),
      });

      if (resp.ok) {
        msg.ack();
      } else {
        msg.retry();
      }
    }
  },
};
```

---

## Anti-patterns

- **Doing all processing synchronously in the `email()` handler** — long-running tasks risk hitting the 30-second CPU time limit.
- **Publishing the raw message payload to every queue** — publish only the fields each consumer needs.
- **Storing a reference to `message.raw` or calling `message.forward()` after the handler returns** — both throw; the stream and the `EmailMessage` object are invalid after the handler resolves.
- **Using a single queue for all consumers** — each consumer gets independent retry behaviour when bound to its own queue.

---

## Gotchas

- `message.raw` is a `ReadableStream` that can only be read once. Buffer it into an `ArrayBuffer` at the top of the handler before any branching logic.
- Cloudflare Queue message payloads must be JSON-serialisable and under 128 KB. For large emails, stage the raw bytes to R2 first and put only the R2 key in the payload.
- `Promise.allSettled()` does not throw if one queue `send()` fails; check each result's `status` field if you need to log or alert on fanout failures.
- `msg.retry()` in a consumer causes the Queue to redeliver the message up to the queue's configured `max_retries` (default 3).

---

## Verification

```bash
# Deploy the producer email Worker
wrangler deploy --name email-fanout src/index.ts

# Deploy each consumer Worker
wrangler deploy --name email-archive-consumer  src/archive-consumer.ts
wrangler deploy --name email-notify-consumer   src/notify-consumer.ts

# Send a test email to the bound address
swaks --from test@gmail.com --to inbox@yourdomain.com \
  --subject "Test queue fanout" --body "Hello from swaks"

# Query D1 to confirm the classify consumer ran
wrangler d1 execute email-index \
  --command "SELECT message_id, category, indexed_at FROM email_index ORDER BY rowid DESC LIMIT 5"
```

---

## Related

- `email-smtp-pipeline-workers-queues.md`
- `email-digest-batching-queues-d1-workers.md`
- `transactional-queue-cloudflare-queues.md`
- `inbound-email-processing.md`

---

## Sources

- Cloudflare Email Routing Workers — https://developers.cloudflare.com/email-routing/email-workers/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
- Cloudflare Workers AI — https://developers.cloudflare.com/workers-ai/
- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
