# Handling Email Bounce and Complaint Webhooks in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your transactional email provider posts bounce and complaint events to a webhook endpoint but you have no durable handler. Without processing these events you continue sending to hard-bounced addresses, ruining sender reputation and risking account suspension. A Cloudflare Worker with D1 persistence handles HMAC verification, parses `bounceType`, writes suppressions, and a Cron Trigger re-enables soft-bounced addresses after a cooldown period.

---

## Context

Email providers (SendGrid, Postmark, MailChannels, AWS SES) send webhook POSTs signed with an HMAC-SHA256 or similar signature in a request header. The Worker must verify this signature before processing the payload to prevent spoofed suppression events. Bounce types differ: `hard` bounces (invalid address, domain does not exist) are permanent and the address must never be retried; `soft` bounces (mailbox full, temporary server error) are transient and the address can be retried after a cooldown. Complaints (spam reports) should also be suppressed indefinitely. A D1 table `email_suppressions` stores these states. A Cron Trigger scheduled every 6 hours queries D1 for soft bounces older than 72 hours and removes the suppression.

---

## Section 1 — D1 Schema & Wrangler Config

```toml
# wrangler.toml
name = "email-bounce-handler"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[vars]
WEBHOOK_HEADER = "X-Webhook-Signature"

# Secret: <redacted-secret> — set via wrangler secret put WEBHOOK_SECRET

[[d1_databases]]
binding = "DB"
database_name = "email-bounces"
database_id   = "<YOUR_D1_DATABASE_ID>"

[triggers]
crons = ["0 */6 * * *"]   # every 6 hours
```

```sql
-- migrations/0001_suppressions.sql
CREATE TABLE IF NOT EXISTS email_suppressions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  email        TEXT    NOT NULL UNIQUE,
  reason       TEXT    NOT NULL CHECK(reason IN ('hard', 'soft', 'complaint')),
  raw_event    TEXT,
  suppressed_at TEXT NOT NULL DEFAULT (datetime('now')),
  retry_after   TEXT   -- NULL for hard/complaint, set for soft
);

CREATE INDEX IF NOT EXISTS idx_email ON email_suppressions(email);
CREATE INDEX IF NOT EXISTS idx_retry ON email_suppressions(retry_after);
```

```bash
npx wrangler d1 create email-bounces
npx wrangler d1 execute email-bounces --file=migrations/0001_suppressions.sql
npx wrangler secret put WEBHOOK_SECRET
```

## Section 2 — Implementation

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
  WEBHOOK_SECRET: string;
  WEBHOOK_HEADER: string;
}

type BounceType = "hard" | "soft" | "complaint";

interface BounceEvent {
  email: string;
  bounceType: BounceType;
  reason?: string;
  timestamp?: string;
}

// --- HMAC verification ---
async function verifySignature(
  secret: string,
  body: string,
  signature: string
): Promise<boolean> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  const sigBytes = hexToBytes(signature);
  return crypto.subtle.verify("HMAC", key, sigBytes, encoder.encode(body));
}

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes;
}

// --- Suppression logic ---
async function upsertSuppression(
  db: D1Database,
  event: BounceEvent
): Promise<void> {
  const retryAfter =
    event.bounceType === "soft"
      ? new Date(Date.now() + 72 * 60 * 60 * 1000).toISOString()
      : null;

  await db
    .prepare(
      `INSERT INTO email_suppressions (email, reason, raw_event, retry_after)
       VALUES (?1, ?2, ?3, ?4)
       ON CONFLICT(email) DO UPDATE SET
         reason       = excluded.reason,
         raw_event    = excluded.raw_event,
         suppressed_at = datetime('now'),
         retry_after  = excluded.retry_after`
    )
    .bind(
      event.email.toLowerCase(),
      event.bounceType,
      JSON.stringify(event),
      retryAfter
    )
    .run();
}

// --- Cron: re-enable soft bounces past retry_after ---
async function processSoftBounceRecovery(db: D1Database): Promise<void> {
  await db
    .prepare(
      `DELETE FROM email_suppressions
       WHERE reason = 'soft'
         AND retry_after IS NOT NULL
         AND retry_after <= datetime('now')`
    )
    .run();
}

// --- Handler ---
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const rawBody = await request.text();
    const signature = request.headers.get(env.WEBHOOK_HEADER) ?? "";

    const valid = await verifySignature(env.WEBHOOK_SECRET, rawBody, signature);
    if (!valid) {
      return new Response("Unauthorized", { status: 401 });
    }

    let events: BounceEvent[];
    try {
      const parsed = JSON.parse(rawBody);
      // Support both single event objects and arrays
      events = Array.isArray(parsed) ? parsed : [parsed];
    } catch {
      return new Response("Bad Request", { status: 400 });
    }

    const writes = events
      .filter((e) => ["hard", "soft", "complaint"].includes(e.bounceType))
      .map((e) => upsertSuppression(env.DB, e));

    await Promise.all(writes);

    return new Response(JSON.stringify({ processed: writes.length }), {
      headers: { "Content-Type": "application/json" },
    });
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await processSoftBounceRecovery(env.DB);
  },
};
```

## Section 3 — Integration Testing

```bash
# Deploy
npx wrangler deploy

# Generate a test HMAC signature
SECRET="your-webhook-secret"
PAYLOAD='{"email":"test@hard-bounce.com","bounceType":"hard"}'
SIG=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

# POST a hard bounce
curl -X POST https://email-bounce-handler.<account>.workers.dev \
  -H 'Content-Type: application/json' \
  -H "X-Webhook-Signature: $SIG" \
  -d "$PAYLOAD"
# Expected: {"processed":1}

# Confirm suppression was written
npx wrangler d1 execute email-bounces \
  --command="SELECT * FROM email_suppressions;"

# Test cron manually
npx wrangler dev --test-scheduled
# In another terminal:
curl "http://localhost:8787/__scheduled?cron=0+*%2F6+*+*+*"
```

---

## Anti-patterns

- **Accepting events without HMAC verification** — An attacker can POST fake hard-bounce events to suppress valid addresses from your send queue; always verify the signature first.
- **Treating all bounces as hard** — Soft bounces from full mailboxes should recover automatically; permanently suppressing them loses real customers.
- **Deleting hard-bounce rows on retry** — Hard-bounce suppressions must be permanent; removing them and re-sending will harm your sender score further.

---

## Gotchas

- The `crypto.subtle` HMAC `verify` returns `false` for a length mismatch rather than throwing; always check the return value, not just the absence of an exception.
- Some providers (SendGrid) use base64-encoded signatures rather than hex; adapt `hexToBytes` accordingly by using `atob()` and converting to `Uint8Array`.
- `scheduled()` runs in a separate invocation from `fetch()`; the D1 binding must appear in `[[d1_databases]]` regardless of which handler uses it.
- Cron Triggers are not available in local `wrangler dev` by default; use `--test-scheduled` flag to expose the `/__scheduled` endpoint.

---

## Verification

```bash
# Check current suppressions
npx wrangler d1 execute email-bounces \
  --command="SELECT email, reason, suppressed_at, retry_after FROM email_suppressions ORDER BY suppressed_at DESC LIMIT 20;"

# Monitor cron executions in Cloudflare Dashboard
# Workers & Pages → email-bounce-handler → Triggers → Cron

# Verify a specific email is suppressed before sending
npx wrangler d1 execute email-bounces \
  --command="SELECT id FROM email_suppressions WHERE email = 'test@hard-bounce.com';"
```

---

## Related

- `workers-inbound-email-spam-filter-d1.md`
- `workers-email-template-r2-handlebars.md`

---

## Sources

- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Web Crypto HMAC — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/verify
