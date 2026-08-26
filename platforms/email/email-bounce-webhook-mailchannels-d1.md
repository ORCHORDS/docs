# Processing MailChannels Bounce Webhooks with Workers and D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Sends that silently bounce degrade your sender reputation and waste MailChannels quota. Processing the MailChannels webhook for bounce events in a Worker allows immediate categorisation (hard/soft/spam), suppression list enforcement, and per-contact bounce tracking in D1 — all without an external service.

---

## Context

MailChannels posts event payloads to a configurable webhook URL whenever a message disposition changes. The request carries an `X-MailChannels-Signature` HMAC-SHA256 header computed over the raw request body using a shared secret. Workers verify this signature before touching any data. Hard bounces (5xx SMTP codes) indicate a permanent delivery failure and must suppress the address immediately; soft bounces (4xx or transient failures) are tracked but allow future retries up to a configured threshold; spam complaints should trigger the same suppression path as hard bounces. A `contacts` table column `is_bounced` gates all outbound sends.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "email-bounce-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[secrets]
# wrangler secret put MAILCHANNELS_WEBHOOK_SECRET
MAILCHANNELS_WEBHOOK_SECRET = ""

[[d1_databases]]
binding = "DB"
database_name = "email-db"
database_id = "YOUR_D1_DATABASE_ID"
```

```sql
CREATE TABLE IF NOT EXISTS email_bounce_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id   TEXT    NOT NULL,
  recipient    TEXT    NOT NULL,
  bounce_type  TEXT    NOT NULL,  -- 'hard' | 'soft' | 'spam'
  smtp_code    INTEGER,
  description  TEXT,
  raw_event    TEXT,
  occurred_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_bounce_recipient ON email_bounce_log(recipient);
CREATE INDEX idx_bounce_message   ON email_bounce_log(message_id);

CREATE TABLE IF NOT EXISTS contacts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  email       TEXT    NOT NULL UNIQUE,
  is_bounced  INTEGER NOT NULL DEFAULT 0,
  soft_count  INTEGER NOT NULL DEFAULT 0,
  updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_contacts_email ON contacts(email);
```

## Section 2 — Signature verification and bounce categorisation

```typescript
export interface Env {
  DB: D1Database;
  MAILCHANNELS_WEBHOOK_SECRET: string;
}

interface MailChannelsEvent {
  event: string;       // e.g. 'bounce', 'deferred', 'spam_report', 'delivered'
  email: string;
  message_id: string;
  smtp_code?: number;
  description?: string;
  timestamp: number;
}

type BounceType = 'hard' | 'soft' | 'spam';

async function verifySignature(
  secret: string,
  body: string,
  signature: string
): Promise<boolean> {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const expected = await crypto.subtle.sign(
    'HMAC',
    key,
    new TextEncoder().encode(body)
  );
  const expectedHex = Array.from(new Uint8Array(expected))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return expectedHex === signature.toLowerCase();
}

function categorizeBounce(event: MailChannelsEvent): BounceType | null {
  if (event.event === 'spam_report') return 'spam';
  if (event.event === 'bounce') {
    const code = event.smtp_code ?? 0;
    if (code >= 500 && code < 600) return 'hard';
    if (code >= 400 && code < 500) return 'soft';
    // Treat unknown bounce codes as hard to be safe
    return 'hard';
  }
  if (event.event === 'deferred') return 'soft';
  return null; // Delivered, click, open — not a bounce
}

async function recordBounce(
  db: D1Database,
  event: MailChannelsEvent,
  bounceType: BounceType
): Promise<void> {
  const rawEvent = JSON.stringify(event);

  await db
    .prepare(
      `INSERT INTO email_bounce_log
         (message_id, recipient, bounce_type, smtp_code, description, raw_event)
       VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(
      event.message_id,
      event.email,
      bounceType,
      event.smtp_code ?? null,
      event.description ?? null,
      rawEvent
    )
    .run();

  if (bounceType === 'hard' || bounceType === 'spam') {
    // Hard suppress
    await db
      .prepare(
        `INSERT INTO contacts (email, is_bounced, updated_at)
         VALUES (?, 1, datetime('now'))
         ON CONFLICT(email) DO UPDATE
           SET is_bounced = 1, updated_at = excluded.updated_at`
      )
      .bind(event.email)
      .run();
  } else {
    // Soft bounce: increment counter; suppress after 3 soft bounces
    await db
      .prepare(
        `INSERT INTO contacts (email, soft_count, updated_at)
         VALUES (?, 1, datetime('now'))
         ON CONFLICT(email) DO UPDATE
           SET soft_count = soft_count + 1,
               is_bounced = CASE WHEN soft_count + 1 >= 3 THEN 1 ELSE is_bounced END,
               updated_at = excluded.updated_at`
      )
      .bind(event.email)
      .run();
  }
}
```

## Section 3 — Webhook fetch handler

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const body = await request.text();
    const signature = request.headers.get('X-MailChannels-Signature') ?? '';

    if (!signature) {
      return new Response('Missing signature', { status: 401 });
    }

    const valid = await verifySignature(
      env.MAILCHANNELS_WEBHOOK_SECRET,
      body,
      signature
    );
    if (!valid) {
      console.warn('Invalid MailChannels webhook signature');
      return new Response('Forbidden', { status: 403 });
    }

    let events: MailChannelsEvent[];
    try {
      const parsed = JSON.parse(body);
      events = Array.isArray(parsed) ? parsed : [parsed];
    } catch {
      return new Response('Bad JSON', { status: 400 });
    }

    for (const event of events) {
      const bounceType = categorizeBounce(event);
      if (bounceType) {
        await recordBounce(env.DB, event, bounceType);
        console.log(`Processed ${bounceType} bounce for ${event.email}`);
      } else {
        console.log(`Ignoring non-bounce event: ${event.event} for ${event.email}`);
      }
    }

    return new Response('OK', { status: 200 });
  },
};

// Suppression check helper — import in your send path
export async function isSuppressed(
  db: D1Database,
  email: string
): Promise<boolean> {
  const row = await db
    .prepare('SELECT is_bounced FROM contacts WHERE email = ?')
    .bind(email)
    .first<{ is_bounced: number }>();
  return row?.is_bounced === 1;
}
```

---

## Anti-patterns

- **Processing the webhook body before verifying the signature** — Parse only after the HMAC check passes; an attacker can craft arbitrary bounce events to suppress legitimate contacts.
- **Treating all bounce events as hard bounces** — Soft bounces (4xx, deferral) are transient; suppressing after the first soft bounce removes addresses that would have been deliverable after a retry.
- **Ignoring spam complaint events** — Spam complaints (`spam_report`) should trigger the same hard suppression as 5xx bounces; failing to suppress after a complaint risks further deliverability harm.
- **Not recording the raw event in D1** — Storing the full JSON payload allows post-hoc analysis and replay if the categorisation logic needs to be updated.

---

## Gotchas

- MailChannels sends webhooks as JSON arrays even when only one event is present; always handle both array and single-object payloads.
- The `X-MailChannels-Signature` value is a lowercase hex string, not a Base64 value — compare accordingly.
- Webhook delivery is not guaranteed exactly-once; the `INSERT OR IGNORE` / `ON CONFLICT` pattern on `email_bounce_log` prevents duplicate rows if the same event is replayed.
- MailChannels may batch multiple events for different recipients in a single POST; iterate the full array rather than processing only `events[0]`.
- The soft-bounce threshold of 3 is configurable; adjust the `>= 3` constant to match your retry policy.

---

## Verification

```bash
# Deploy the Worker
npx wrangler deploy

# Generate a test signature (replace YOUR_SECRET)
BODY='[{"event":"bounce","email":"bad@example.com","message_id":"msg-001","smtp_code":550,"timestamp":1724500000}]'
SIG=$(echo -n "$BODY" | openssl dgst -sha256 -hmac 'YOUR_SECRET' | awk '{print $2}')

# POST the test event
curl -s -X POST https://your-worker.workers.dev/ \
     -H 'Content-Type: application/json' \
     -H "X-MailChannels-Signature: $SIG" \
     -d "$BODY"

# Check D1 tables
npx wrangler d1 execute email-db \
  --command "SELECT * FROM email_bounce_log ORDER BY occurred_at DESC LIMIT 5;"

npx wrangler d1 execute email-db \
  --command "SELECT email, is_bounced, soft_count FROM contacts WHERE email = 'bad@example.com';"
```

---

## Related

- `email-unsubscribe-list-header-workers.md`
- `email-rate-limiting-kv-mailchannels-workers.md`

---

## Sources

- MailChannels Webhooks — https://docs.mailchannels.net/transactional-email/webhooks
- Cloudflare Workers D1 — https://developers.cloudflare.com/d1/
- SMTP Reply Codes RFC 5321 — https://www.rfc-editor.org/rfc/rfc5321
