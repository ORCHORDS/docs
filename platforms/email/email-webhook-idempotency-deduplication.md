# Email Webhook Idempotency and Deduplication

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

An ESP fires a `bounce` webhook event and the endpoint returns a 500 error. The ESP
retries the event three more times over the next hour. The Worker processes the event on
the first retry but the endpoint crashes on the third delivery — so the event is
processed twice. A subscriber is double-suppressed (harmless in this case), a billing
event fires twice (catastrophic), or a database row that should be inserted once now has
two identical entries. The same failure mode applies to ESP webhooks for opens, clicks,
complaints, deliveries, and unsubscribes: all major ESPs (SendGrid, Resend, Postmark,
Mailgun, AWS SES) retry failed webhook deliveries for minutes to hours, and they cannot
guarantee exactly-once delivery at the HTTP layer.

## Context

HTTP webhooks are at-least-once by design. The sending party retries until it receives
an HTTP 2xx within a timeout. If the receiver processes the request but crashes before
responding, the event is retried even though it was already handled. A correctly designed
webhook consumer must be **idempotent**: processing the same event payload any number of
times has exactly the same observable outcome as processing it once. Idempotency is
implemented by recording a durable `event_id` before acting on the event, and skipping
all processing if the `event_id` is already recorded.

Cloudflare Workers + D1 implement a fast, low-latency idempotency store without
requiring a Redis cluster.

## ESP Event ID Headers

Each major ESP includes a unique event identifier in the webhook payload or headers:

| ESP         | Event ID location                            | Example field            |
|-------------|----------------------------------------------|--------------------------|
| SendGrid    | JSON body `sg_event_id` per event            | `"sg_event_id": "abc123"` |
| Resend      | JSON body `data.email_id` + event `type`     | `"email_id": "re_..."`   |
| Postmark    | JSON body `MessageID` per record             | `"MessageID": "abc-..."`  |
| Mailgun     | JSON body `event-data.id`                    | `"id": "Ase7i2zsRYeDXztHJ"` |
| AWS SES     | SNS `Message.mail.messageId` per notification | SNS deduplication via `TopicArn` + `MessageId` |

The idempotency key should be composite: `{espName}:{eventType}:{eventId}` to avoid
collisions if the same message-id appears across different event types or ESPs.

## D1 Idempotency Store

```sql
CREATE TABLE webhook_events (
  idempotency_key TEXT    PRIMARY KEY,      -- '{esp}:{type}:{eventId}'
  received_at     INTEGER NOT NULL,         -- Unix ms
  processed_at    INTEGER,                  -- NULL = in-flight; set on success
  payload_hash    TEXT    NOT NULL,         -- SHA-256 of raw body for audit
  status          TEXT    NOT NULL DEFAULT 'pending'  -- 'pending' | 'processed' | 'failed'
);

-- Auto-prune old records after 30 days (enforced by cleanup cron)
CREATE INDEX idx_we_received_at ON webhook_events(received_at);
```

Keep records for 30 days — long enough to cover any ESP retry window (maximum is
typically 72 hours) plus a safety margin.

## Worker Implementation

```typescript
// src/webhook-handler.ts
import { createHash } from 'crypto';

interface Env {
  WEBHOOK_DB: D1Database;
  WEBHOOK_SECRET: string; // for HMAC verification
}

interface ESPEvent {
  type: string;
  eventId: string;
  email?: string;
  timestamp?: number;

}

function extractEventId(body: unknown, esp: string): string | null {
  if (esp === 'sendgrid') {
    const arr = body as Array<{ sg_event_id: string; event: string }>;
    return arr[0]?.sg_event_id ?? null;
  }
  if (esp === 'resend') {
    const obj = body as { type: string; data: { email_id: string } };
    return `${obj.type}:${obj.data.email_id}`;
  }
  if (esp === 'postmark') {
    const obj = body as { MessageID: string; RecordType: string };
    return `${obj.RecordType}:${obj.MessageID}`;
  }
  if (esp === 'mailgun') {
    const obj = body as { 'event-data': { id: string; event: string } };
    return `${obj['event-data'].event}:${obj['event-data'].id}`;
  }
  return null;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const esp = new URL(request.url).searchParams.get('esp') ?? 'unknown';
    const rawBody = await request.text();

    // 1. Verify HMAC signature
    if (!verifySignature(request, rawBody, env.WEBHOOK_SECRET, esp)) {
      return new Response('Forbidden', { status: 403 });
    }

    const body = JSON.parse(rawBody);
    const eventId = extractEventId(body, esp);
    if (!eventId) {
      return new Response('Missing event ID', { status: 400 });
    }

    const idempotencyKey = `${esp}:${eventId}`;
    const payloadHash = createHash('sha256').update(rawBody).digest('hex');
    const now = Date.now();

    // 2. Attempt to INSERT the idempotency record
    //    OR IGNORE means a duplicate key is a no-op and we skip processing
    const result = await env.WEBHOOK_DB.prepare(`
      INSERT OR IGNORE INTO webhook_events
        (idempotency_key, received_at, payload_hash, status)
      VALUES (?, ?, ?, 'pending')
    `).bind(idempotencyKey, now, payloadHash).run();

    if (result.meta.rows_written === 0) {
      // Already seen — return 200 so the ESP stops retrying
      return new Response(JSON.stringify({ duplicate: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // 3. Process the event asynchronously so we can return 200 quickly
    ctx.waitUntil(
      processEvent(body, esp, env)
        .then(() =>
          env.WEBHOOK_DB.prepare(
            "UPDATE webhook_events SET processed_at = ?, status = 'processed' WHERE idempotency_key = ?"
          ).bind(Date.now(), idempotencyKey).run()
        )
        .catch(async err => {
          await env.WEBHOOK_DB.prepare(
            "UPDATE webhook_events SET status = 'failed' WHERE idempotency_key = ?"
          ).bind(idempotencyKey).run();
          console.error('Webhook processing failed:', err);
        })
    );

    return new Response(JSON.stringify({ accepted: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

`ctx.waitUntil()` allows the Worker to return HTTP 200 immediately (stopping the ESP
retry clock) while processing continues asynchronously. The `INSERT OR IGNORE` idiom
in D1/SQLite is atomic: only one concurrent write wins the race for a given key.

## Handling the Race Condition Window

Between the `INSERT OR IGNORE` and the actual event processing there is a small window
where a concurrent retry might see the `pending` record and treat it as already-processed
while the first invocation is still running. To handle this:

```typescript
async function getEventStatus(db: D1Database, key: string): Promise<string | null> {
  const row = await db.prepare(
    'SELECT status FROM webhook_events WHERE idempotency_key = ?'
  ).bind(key).first<{ status: string }>();
  return row?.status ?? null;
}
```

If `status = 'pending'` and `received_at` is more than 30 seconds ago, assume the first
invocation crashed without updating the status and re-process:

```typescript
const status = await getEventStatus(env.WEBHOOK_DB, idempotencyKey);
const isStuck = status === 'pending' && (now - existingReceivedAt) > 30_000;
if (status === 'processed' || (status === 'pending' && !isStuck)) {
  return new Response(JSON.stringify({ duplicate: true }), { status: 200 });
}
```

## Signature Verification Per ESP

Always verify the webhook signature before touching the database:

```typescript
async function verifyResendSignature(
  request: Request,
  rawBody: string,
  secret: string,
): Promise<boolean> {
  const sig = request.headers.get('svix-signature') ?? '';
  const timestamp = request.headers.get('svix-timestamp') ?? '';
  const signedContent = `${timestamp}.${rawBody}`;
  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['verify']
  );
  const expectedSig = await crypto.subtle.sign(
    'HMAC', key, new TextEncoder().encode(signedContent)
  );
  const expectedHex = [...new Uint8Array(expectedSig)]
    .map(b => b.toString(16).padStart(2, '0')).join('');
  // sig may contain multiple space-separated candidates
  return sig.split(' ').some(s => s.replace(/^v1,/, '') === expectedHex);
}
```

## Cleanup Cron

Prune processed records older than 30 days:

```typescript
// src/webhook-cleanup.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const cutoff = Date.now() - 30 * 86_400_000;
    await env.WEBHOOK_DB.prepare(
      "DELETE FROM webhook_events WHERE received_at < ? AND status IN ('processed', 'failed')"
    ).bind(cutoff).run();
  },
};
```

Retain `failed` records longer if you need a manual re-processing queue.

## Anti-patterns

- **Using only message content as the idempotency key**: two different events for the
  same email address (e.g. two clicks) would collide if the key is derived from
  recipient email alone. Always include the ESP-assigned event ID.
- **Returning non-200 after processing**: if the Worker processes the event successfully
  but returns a 500, the ESP retries and the Worker processes it again. The idempotency
  check will catch this — but returning an incorrect status code creates unnecessary
  duplicate attempts and load.
- **Storing raw webhook payloads in D1**: large JSON bodies (up to 1 MB for batch
  SendGrid events) make the idempotency table expensive and slow. Store only the
  `idempotency_key` and a `payload_hash`; the full payload is in the ESP's own activity
  log for debugging.
- **No signature verification**: without HMAC verification, any party that knows your
  webhook URL can fabricate suppression events, triggering mass unsubscribes. Always
  verify before inserting into the idempotency store.

## Gotchas

- **SendGrid batches events**: a single webhook POST from SendGrid may contain up to 1000
  events in a JSON array. Each event has its own `sg_event_id`. Your handler must
  iterate the array and check each event ID separately.
- **Resend uses Svix**: Resend's webhook infrastructure is built on Svix, which uses its
  own multi-signature header format. The signature header may contain a comma-separated
  list of candidate signatures from a rolling key window.
- **D1 INSERT OR IGNORE is SQLite-specific**: the ON CONFLICT clause behaviour differs
  from PostgreSQL. In D1, `INSERT OR IGNORE` silently discards conflicting rows; in
  Postgres the equivalent is `INSERT ... ON CONFLICT DO NOTHING`.
- **Workers CPU time and `waitUntil`**: `ctx.waitUntil()` extends the lifetime of the
  Worker invocation after the response is returned, but is still subject to the
  Worker's maximum wall-clock CPU limit (30 s on paid plans). Heavy processing should be
  offloaded to a Queue consumer.

## Verification

1. POST the same webhook payload twice with identical event IDs; confirm only one row
   exists in `webhook_events` and the second request returns `{ "duplicate": true }`.
2. Simulate a processing crash by throwing inside `processEvent`; confirm `status`
   remains `'failed'` and the row is not deleted by the cleanup cron until 30 days pass.
3. Submit a POST with an invalid HMAC signature; confirm the Worker returns 403 and no
   database row is written.
4. Submit a SendGrid batch with 10 events; confirm 10 rows appear in `webhook_events`.

## Related

- `sendgrid-event-webhook.md`
- `ses-bounce-complaint-webhooks.md`
- `email-queue-architecture.md`
- `suppression-list-management.md`
- `email-retry-exponential-backoff.md`

## Sources

- SendGrid Event Webhook docs: https://docs.sendgrid.com/for-developers/tracking-events/event
- Resend webhook docs: https://resend.com/docs/dashboard/webhooks/introduction
- Postmark webhooks docs: https://postmarkapp.com/developer/webhooks/webhooks-overview
- Svix webhook signatures: https://docs.svix.com/receiving/verifying-payloads/how
- Cloudflare Workers `waitUntil`: https://developers.cloudflare.com/workers/runtime-apis/context/
