# Email Suppression List Management with Workers + KV

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your sending reputation degrades because you continue sending to addresses that have previously unsubscribed, hard-bounced, or generated a spam complaint. ISPs penalise senders that ignore these signals. You need a global suppression store that is checked before every outbound email, updated by webhooks from MailChannels/SendGrid/Postmark, and queryable for GDPR data-subject requests with timestamped proof of suppression.

## Context

Cloudflare Workers KV is an eventually consistent key-value store with reads typically under 1 ms after the first read in a region (the value is cached at the edge closest to the Worker). It is ideal for suppression lists because: reads are extremely fast (suppression checks happen on the hot path of every send), the data is write-once / read-many (a suppressed address rarely comes back), and it scales globally without operator effort. KV values can carry metadata (timestamps, reasons) and TTLs (for soft suppressions that expire). Each KV namespace holds up to 1 billion keys.

Suppressions fall into three classes with different severity:
- **Unsubscribe** — recipient opted out; must be honoured per CAN-SPAM / GDPR.
- **Hard bounce** — address does not exist; sending again damages reputation immediately.
- **Complaint** — recipient marked as spam; ISP FBL signal, high reputation risk.

## Solution

### KV Namespace Binding

```toml
# wrangler.toml
name = "email-sender"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "SUPPRESSION"
id = "<your-kv-namespace-id>"
preview_id = "<your-preview-kv-namespace-id>"
```

### Suppression Record Schema

KV key: `suppress:<email-address-lowercased>`

KV value (JSON string):
```json
{
  "email": "user@example.com",
  "reason": "unsubscribe" | "hard_bounce" | "complaint",
  "source": "mailchannels_webhook" | "user_request" | "bulk_import" | "manual",
  "suppressedAt": "2026-08-24T10:00:00.000Z",
  "messageId": "optional-originating-message-id",
  "notes": "optional human-readable detail"
}
```

### Suppression Check Before Send

```typescript
// src/suppression.ts
export interface Env {
  SUPPRESSION: KVNamespace;
}

export interface SuppressionRecord {
  email: string;
  reason: 'unsubscribe' | 'hard_bounce' | 'complaint';
  source: string;
  suppressedAt: string;
  messageId?: string;
  notes?: string;
}

/**
 * Returns the suppression record if the address is suppressed, null otherwise.
 * Uses the KV cache: reads are served from the edge, not the origin store.
 */
export async function checkSuppression(
  env: Env,
  email: string
): Promise<SuppressionRecord | null> {
  const key = `suppress:${email.toLowerCase().trim()}`;
  const value = await env.SUPPRESSION.get(key, { type: 'json' });
  return value as SuppressionRecord | null;
}

/**
 * Suppress an address. Idempotent — overwrites if already present.
 * Hard bounces and complaints do NOT get a TTL (permanent).
 * Unsubscribes also never expire unless the user re-subscribes with explicit consent.
 */
export async function suppress(
  env: Env,
  record: Omit<SuppressionRecord, 'suppressedAt'>
): Promise<void> {
  const key = `suppress:${record.email.toLowerCase().trim()}`;
  const full: SuppressionRecord = {
    ...record,
    email: record.email.toLowerCase().trim(),
    suppressedAt: new Date().toISOString(),
  };
  // KV put with no expirationTtl = permanent entry.
  await env.SUPPRESSION.put(key, JSON.stringify(full));
}

/**
 * Remove a suppression (re-subscribe flow — requires explicit user consent proof).
 * In most jurisdictions re-subscription requires a confirmed double opt-in.
 */
export async function removeSuppression(
  env: Env,
  email: string
): Promise<void> {
  const key = `suppress:${email.toLowerCase().trim()}`;
  await env.SUPPRESSION.delete(key);
}
```

### Send Guard — Integrate Suppression Check into Send Path

```typescript
// src/send.ts
import { Env, checkSuppression } from './suppression';

export interface SendRequest {
  to: string;
  subject: string;
  html: string;
  text: string;
  messageId: string;
}

export async function guardedSend(
  env: Env,
  req: SendRequest
): Promise<{ sent: boolean; reason?: string }> {
  const suppressed = await checkSuppression(env, req.to);
  if (suppressed) {
    console.warn(`Suppressed send to ${req.to} (${suppressed.reason})`);
    return { sent: false, reason: suppressed.reason };
  }

  const response = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: req.to }] }],
      from: { email: 'noreply@example.com', name: 'Orchords' },
      subject: req.subject,
      content: [
        { type: 'text/plain', value: req.text },
        { type: 'text/html', value: req.html },
      ],
      headers: { 'X-Message-ID': req.messageId },
    }),
  });

  if (!response.ok) {
    throw new Error(`MailChannels error: ${response.status}`);
  }

  return { sent: true };
}
```

### Bulk Suppression Import

```typescript
// src/bulk-import.ts
// Called from a one-off Worker invocation or a CI script using wrangler kv bulk.
import { Env, suppress } from './suppression';

/**
 * Import a newline-delimited CSV of suppressions.
 * Format: email,reason,source
 * e.g.: user@example.com,hard_bounce,legacy_system
 */
export async function bulkImport(env: Env, csv: string): Promise<number> {
  const lines = csv.split('\n').filter(Boolean);
  let count = 0;

  // KV bulk-write: batch into groups of 100 parallel puts.
  const BATCH = 100;
  for (let i = 0; i < lines.length; i += BATCH) {
    const batch = lines.slice(i, i + BATCH);
    await Promise.all(
      batch.map((line) => {
        const [email, reason, source] = line.split(',');
        if (!email || !reason) return Promise.resolve();
        return suppress(env, {
          email: email.trim(),
          reason: (reason.trim() as SuppressionRecord['reason']) ?? 'unsubscribe',
          source: source?.trim() ?? 'bulk_import',
        });
      })
    );
    count += batch.length;
  }
  return count;
}

// Re-export type for convenience.
type SuppressionRecord = import('./suppression').SuppressionRecord;
```

### MailChannels Webhook Handler

```typescript
// src/webhook.ts
// Register this endpoint as your MailChannels event webhook URL.
import { Env, suppress } from './suppression';

interface MailChannelsEvent {
  event: 'bounce' | 'unsubscribe' | 'spam_report' | 'delivered' | 'open' | 'click';
  email: string;
  timestamp: number; // Unix epoch seconds
  message_id?: string;
  bounce_type?: 'hard' | 'soft';
}

export async function handleWebhook(
  request: Request,
  env: Env
): Promise<Response> {
  // Validate shared secret from MailChannels.
  const secret = <redacted-secret>'X-Webhook-Secret');
  if (secret !== (env as unknown as { WEBHOOK_SECRET: string }).WEBHOOK_SECRET) {
    return new Response('Unauthorized', { status: 401 });
  }

  const events: MailChannelsEvent[] = await request.json();

  await Promise.all(
    events.map(async (evt) => {
      if (evt.event === 'bounce' && evt.bounce_type === 'hard') {
        await suppress(env, {
          email: evt.email,
          reason: 'hard_bounce',
          source: 'mailchannels_webhook',
          messageId: evt.message_id,
        });
      } else if (evt.event === 'unsubscribe') {
        await suppress(env, {
          email: evt.email,
          reason: 'unsubscribe',
          source: 'mailchannels_webhook',
          messageId: evt.message_id,
        });
      } else if (evt.event === 'spam_report') {
        await suppress(env, {
          email: evt.email,
          reason: 'complaint',
          source: 'mailchannels_webhook',
          messageId: evt.message_id,
        });
      }
      // Delivered / open / click events are ignored for suppression purposes.
    })
  );

  return new Response(JSON.stringify({ ok: true }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
```

### GDPR Suppression Proof Endpoint

```typescript
// src/gdpr.ts
// Returns proof that an email is suppressed, for data-subject requests.
import { Env, checkSuppression } from './suppression';

export async function suppressionProof(
  env: Env,
  email: string
): Promise<Response> {
  const record = await checkSuppression(env, email);
  if (!record) {
    return new Response(
      JSON.stringify({ suppressed: false, email: email.toLowerCase() }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  }
  // Return full record as proof artifact (can be saved to PDF for regulators).
  return new Response(
    JSON.stringify({ suppressed: true, ...record }),
    { headers: { 'Content-Type': 'application/json' } }
  );
}
```

## Implementation Details

- KV reads are served from the nearest Cloudflare PoP after the first write propagates (eventual consistency, typically < 60 s globally). For suppression this is acceptable: a rare race condition where an unsubscribe hasn't propagated yet is far less harmful than checking a slow external database on every send.
- Normalise email addresses before keying: `email.toLowerCase().trim()`. This prevents `User@Example.com` and `user@example.com` from bypassing suppression.
- KV `list()` can enumerate suppressions for batch audits. Keys use the `suppress:` prefix so they can be listed with `prefix: 'suppress:'` and paginated with `cursor`.
- For GDPR Article 17 (right to erasure), deleting the KV key removes all stored personal data. Keep an anonymised audit log (hash of address + suppression timestamp) in D1 separately if you need erasure proof without re-identifying the subject.
- Webhook endpoints must be idempotent: the same event delivered twice should not cause errors. Because `suppress()` is an unconditional KV put, it is naturally idempotent.

## Anti-patterns

- **Checking suppression after enqueueing** — the check must happen before any send attempt, not as an afterthought in the consumer.
- **Storing suppressions in a SQL database and querying per-send** — latency is 5–50× higher than KV; at 1 000 sends/s this becomes a bottleneck.
- **Using soft-bounce (mailbox full, temporary failure) to trigger permanent suppression** — only hard bounces warrant permanent suppression. Soft bounce counts should be tracked separately with a counter in KV and suppression triggered only after N consecutive soft bounces (typically 3–5).
- **Deleting suppression on user "re-subscribe" without double opt-in confirmation** — violates CAN-SPAM and GDPR consent requirements.
- **Logging full email addresses in Worker log streams** — email addresses are PII. Hash them (SHA-256) before logging.

## Gotchas

- KV has a 25 MiB value size limit, but suppression records are <500 bytes. Keys are up to 512 bytes; email addresses are well within that.
- `kv.get()` returns `null` (not an error) when the key does not exist. Always null-check the return value.
- Workers KV `list()` has a maximum `limit` of 1 000 per call. For bulk exports of large suppression lists, paginate with `cursor`.
- KV writes from a Worker are not immediately visible to other Workers in the same isolate pool due to eventual consistency. Do not write then immediately read back in a test and expect the new value — add a small delay or use the REST API in tests.
- The `{ type: 'json' }` option on `kv.get()` automatically parses JSON and returns `null` on parse failure. If the stored value is malformed, you get `null` back, not an exception.

## Verification

```bash
# Create KV namespace
wrangler kv:namespace create SUPPRESSION

# Manually add a suppression
wrangler kv:key put --binding=SUPPRESSION \
  'suppress:test@example.com' \
  '{"email":"test@example.com","reason":"hard_bounce","source":"manual","suppressedAt":"2026-08-24T00:00:00.000Z"}'

# Verify it is present
wrangler kv:key get --binding=SUPPRESSION 'suppress:test@example.com'

# Test send guard (should return sent:false)
curl -X POST http://localhost:8787/send \
  -H 'Content-Type: application/json' \
  -d '{"to":"test@example.com","subject":"Test","html":"<p>hi</p>","text":"hi","messageId":"abc"}'

# Test webhook
curl -X POST http://localhost:8787/webhook \
  -H 'X-Webhook-Secret: <redacted-secret>' \
  -H 'Content-Type: application/json' \
  -d '[{"event":"unsubscribe","email":"new@example.com","timestamp":1724457600}]'
```

## Related

- `documentation/docs/policies/email/workers-transactional-email-queue.md`
- `documentation/docs/policies/email/workers-email-open-tracking-pixel.md`
- Cloudflare Workers KV docs: https://developers.cloudflare.com/kv/
- CAN-SPAM Act compliance: https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- GDPR Article 21 (right to object to processing): https://gdpr-info.eu/art-21-gdpr/

## Sources

- Cloudflare KV Workers API docs (2025)
- MailChannels event webhook documentation (2025)
- FTC CAN-SPAM compliance guide (2024)
- GDPR.eu Article 17 and 21 summaries
