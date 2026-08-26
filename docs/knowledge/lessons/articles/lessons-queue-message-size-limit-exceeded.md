# Queue Message Size Limit Exceeded: Silent Drop of Email Attachment Payloads

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

The customer notification pipeline began silently losing approximately 12% of outbound email jobs shortly after a feature shipped that attached PDF order confirmations to the queue message as base64-encoded strings. No error was surfaced in the producer Worker; consumers simply never received those messages. Customer-support tickets about missing order confirmation emails increased by 15× over two days before the root cause was identified.

---

## Context

Cloudflare Queues enforces a hard per-message size limit of 128 KB. When a message exceeds this limit, the `env.QUEUE.send()` call resolves without throwing — the message is silently dropped and never delivered to consumers. There is no built-in dead-letter mechanism for oversized messages; they vanish without a trace in the producer. Order confirmation PDFs range from 80 KB to 350 KB when base64-encoded, and the JSON envelope (recipient data, template variables) added another 2–5 KB. Roughly 12% of orders had PDFs large enough to push the payload over 128 KB.

---

## Root Cause: Payload Size Not Validated Before `env.QUEUE.send()`

The producer encoded the PDF as base64 and embedded it directly in the Queue message:

```typescript
// BEFORE — dangerous: no size check before send()
interface EmailJob {
  to: string;
  subject: string;
  templateId: string;
  vars: Record<string, string>;
  attachmentB64: string;     // ← Can be 80–350 KB after base64 encoding
  attachmentName: string;
}

export async function enqueueConfirmationEmail(
  env: Env,
  orderId: string,
  recipientEmail: string,
  pdfBytes: Uint8Array
): Promise<void> {
  const attachmentB64 = btoa(String.fromCharCode(...pdfBytes));

  const job: EmailJob = {
    to: recipientEmail,
    subject: `Order ${orderId} confirmed`,
    templateId: 'order-confirmation-v2',
    vars: { orderId },
    attachmentB64,           // embeds potentially 350 KB of base64
    attachmentName: `order-${orderId}.pdf`,
  };

  // send() resolves silently even if the message is > 128 KB
  await env.EMAIL_QUEUE.send(job);
  // No exception here — you will never know the message was dropped
}
```

The silence of `send()` on oversized messages is the core hazard. The Cloudflare Queues documentation notes the limit but does not currently throw a runtime error for exceeding it.

---

## Fix: Size Check with R2 Staging Fallback + Dead Letter Queue Monitoring

### Step 1 — Validate size before every `send()` and use R2 staging for large payloads

```typescript
const QUEUE_MAX_BYTES = 120 * 1024; // 120 KB — leave 8 KB buffer below 128 KB hard limit

interface EmailJobSmall {
  to: string;
  subject: string;
  templateId: string;
  vars: Record<string, string>;
  attachmentR2Key?: string;  // reference, not the bytes
  attachmentName?: string;
}

export async function enqueueConfirmationEmailSafe(
  env: Env,
  orderId: string,
  recipientEmail: string,
  pdfBytes: Uint8Array
): Promise<void> {
  let attachmentR2Key: string | undefined;

  // Stage large attachments in R2; store only the key in the Queue message
  const base64Size = Math.ceil(pdfBytes.byteLength * (4 / 3));
  if (base64Size > 80 * 1024) {
    attachmentR2Key = `email-attachments/${orderId}/confirmation.pdf`;
    await env.EMAIL_ATTACHMENTS.put(attachmentR2Key, pdfBytes, {
      httpMetadata: { contentType: 'application/pdf' },
      customMetadata: { orderId, expiresAfter: '7d' },
    });
    console.log(
      `[queue] PDF staged to R2 at ${attachmentR2Key} (${pdfBytes.byteLength} bytes)`
    );
  }

  const job: EmailJobSmall = {
    to: recipientEmail,
    subject: `Order ${orderId} confirmed`,
    templateId: 'order-confirmation-v2',
    vars: { orderId },
    attachmentR2Key,
    attachmentName: `order-${orderId}.pdf`,
  };

  // Validate serialised size BEFORE calling send()
  const serialised = JSON.stringify(job);
  const byteLen = new TextEncoder().encode(serialised).byteLength;

  if (byteLen > QUEUE_MAX_BYTES) {
    // This should never happen after R2 staging, but fail loudly if it does
    throw new Error(
      `Queue message too large: ${byteLen} bytes (limit ${QUEUE_MAX_BYTES}). ` +
      `Job: ${JSON.stringify({ orderId, to: recipientEmail })}`
    );
  }

  await env.EMAIL_QUEUE.send(job);
  console.log(`[queue] email job enqueued for order=${orderId} (${byteLen} bytes)`);
}

// Consumer: fetch attachment from R2 when present
export async function consumeEmailJob(
  batch: MessageBatch<EmailJobSmall>,
  env: Env
): Promise<void> {
  for (const msg of batch.messages) {
    const job = msg.body;
    try {
      let attachmentBytes: Uint8Array | undefined;

      if (job.attachmentR2Key) {
        const obj = await env.EMAIL_ATTACHMENTS.get(job.attachmentR2Key);
        if (!obj) throw new Error(`R2 attachment not found: ${job.attachmentR2Key}`);
        attachmentBytes = new Uint8Array(await obj.arrayBuffer());
      }

      await sendEmail(env, {
        to: job.to,
        subject: job.subject,
        templateId: job.templateId,
        vars: job.vars,
        attachment: attachmentBytes
          ? { bytes: attachmentBytes, name: job.attachmentName! }
          : undefined,
      });

      // Clean up R2 object after successful send
      if (job.attachmentR2Key) {
        await env.EMAIL_ATTACHMENTS.delete(job.attachmentR2Key);
      }

      msg.ack();
    } catch (err) {
      console.error(`[queue] failed to process email job: ${String(err)}`);
      msg.retry();
    }
  }
}
```

### Step 2 — Dead Letter Queue for retry exhaustion monitoring

```typescript
// wrangler.toml snippet (add alongside your main queue binding)
// [[queues.consumers]]
// queue = "email-queue"
// dead_letter_queue = "email-dlq"
// max_retries = 3

// DLQ consumer: alert and persist failures for manual triage
export async function consumeDlq(
  batch: MessageBatch<EmailJobSmall>,
  env: Env
): Promise<void> {
  for (const msg of batch.messages) {
    const job = msg.body;

    console.error(
      `[dlq] email job permanently failed after max retries: order=${job.vars?.orderId ?? 'unknown'} to=${job.to}`
    );

    // Persist to a failures table for customer-support triage
    await env.DB.prepare(
      `INSERT INTO failed_email_jobs
         (id, payload_json, failed_at)
       VALUES (?, ?, datetime('now'))`
    )
      .bind(crypto.randomUUID(), JSON.stringify(job))
      .run();

    // Emit alert metric
    env.ANALYTICS.writeDataPoint({
      blobs: ['email_dlq', job.vars?.orderId ?? 'unknown'],
      doubles: [1],
      indexes: ['dlq_failures'],
    });

    msg.ack(); // Ack DLQ messages so they don't loop forever
  }
}
```

---

## Monitoring / Detection

```typescript
// Add a size-check utility to every queue producer in your codebase
export function assertQueuePayloadSize<T>(payload: T, label: string): void {
  const LIMIT = 120 * 1024;
  const json = JSON.stringify(payload);
  const bytes = new TextEncoder().encode(json).byteLength;

  if (bytes > LIMIT) {
    throw new Error(
      `[queue] ${label} payload too large: ${(bytes / 1024).toFixed(1)} KB > ${LIMIT / 1024} KB limit. ` +
      'Move large blobs to R2 and include only the key in the message.'
    );
  }

  if (bytes > LIMIT * 0.8) {
    console.warn(
      `[queue] ${label} payload approaching limit: ${(bytes / 1024).toFixed(1)} KB`
    );
  }
}

// Usage in any producer:
async function enqueueAnyJob(env: Env, job: unknown): Promise<void> {
  assertQueuePayloadSize(job, 'email-job');
  await env.EMAIL_QUEUE.send(job);
}

// Track DLQ depth via Cron Trigger + D1 query
export async function reportDlqDepth(env: Env): Promise<void> {
  const row = await env.DB
    .prepare(
      `SELECT COUNT(*) as cnt
         FROM failed_email_jobs
        WHERE failed_at > datetime('now', '-1 hour')`
    )
    .first<{ cnt: number }>();

  const count = row?.cnt ?? 0;
  if (count > 0) {
    console.error(`[dlq] ${count} email jobs failed in the last hour`);
  }

  env.ANALYTICS.writeDataPoint({
    blobs: ['dlq_depth'],
    doubles: [count],
    indexes: ['email_dlq'],
  });
}
```

---

## Anti-patterns

- **Embedding binary data as base64 in Queue messages** — Base64 inflates size by ~33%; combine that with JSON overhead and you easily exceed 128 KB. Always use R2 for binary payloads.
- **Assuming `send()` throws on oversized messages** — It does not (as of mid-2026). Always validate size before calling `send()`.
- **Not configuring a Dead Letter Queue** — Without a DLQ, messages that fail all retries disappear silently. Always set `dead_letter_queue` in your consumer configuration.
- **Deleting R2 staging objects before the consumer confirms success** — If the consumer fails and retries, the R2 object must still be present. Delete only after `msg.ack()`.

---

## Gotchas

- The 128 KB limit applies to the serialised message bytes, not the JavaScript object size. Always measure with `new TextEncoder().encode(JSON.stringify(payload)).byteLength`.
- `btoa()` in Workers only handles Latin-1 strings; use `Buffer.from(bytes).toString('base64')` in Node-compatible contexts or encode Uint8Array chunks manually for binary safety.
- R2 staging objects must be cleaned up; they accrue storage costs and are not automatically expired. Set a lifecycle rule or delete them explicitly in the consumer.
- Queue `send()` is not transactional with D1 writes. If the `send()` call follows a successful DB write, use a background retry or a transactional outbox pattern to avoid the DB commit succeeding but the queue enqueue failing.
- DLQ messages cannot be retried automatically — they require manual reprocessing or a secondary worker that reads from the DLQ and requeues.

---

## Verification

```bash
# Confirm queue binding names in wrangler.toml
grep -A5 'queues' wrangler.toml

# Test size validation locally with a synthetic large payload
node -e "
const payload = { to: 'a@b.com', attachmentB64: Buffer.alloc(100*1024, 65).toString('base64') };
const bytes = Buffer.byteLength(JSON.stringify(payload));
console.log('Payload bytes:', bytes, '(limit: 131072)');
"

# Deploy and send a test message under the limit
curl -s -X POST https://your-worker.example.com/email/test \
  -H 'Content-Type: application/json' \
  -d '{"orderId":"test-001","to":"test@example.com"}' | jq .

# Check DLQ depth metric
npx wrangler analytics-engine query \
  --dataset email_dlq \
  --query "SELECT SUM(double1) as dlq_total FROM DATASET WHERE blob1='dlq_depth'"

# Verify failed_email_jobs table is empty after a clean run
npx wrangler d1 execute <DB_NAME> --remote \
  --command "SELECT COUNT(*) as failures FROM failed_email_jobs WHERE failed_at > datetime('now', '-1 hour')"
```

---

## Related

- `lessons-workers-memory-limit-large-payload.md`
- `lessons-d1-eventual-consistency-production-incident.md`

---

## Sources

- Cloudflare Queues Message Size Limits — https://developers.cloudflare.com/queues/platform/limits/
- Cloudflare Queues Dead Letter Queues — https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- Cloudflare R2 Workers Binding — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
