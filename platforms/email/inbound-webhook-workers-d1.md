# Inbound Email Webhook Processing with Cloudflare Workers and D1

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

## Symptom

Your application needs to receive inbound emails — customer replies, form submissions,
or notification responses — and store structured data for downstream processing. Running
a Node.js server or Lambda just to parse a `multipart/form-data` webhook is expensive
when you already use Cloudflare Workers for other services.

## Context

SendGrid Inbound Parse and Resend's inbound email product both POST parsed email data
to an HTTPS endpoint as `multipart/form-data` (SendGrid) or JSON (Resend). A Cloudflare
Worker can receive these payloads, verify the provider's signature, parse the fields, and
write structured rows to D1 — all at the edge with no persistent server.

D1 gives you relational storage with full SQL, making it trivial to JOIN inbound messages
to existing user records, threads, or tickets. Combined with Cloudflare Queues you can fan
out to async processors without blocking the HTTP response.

Key constraints:
- Workers have a 128 MB memory limit; avoid buffering large attachment binaries in the
  Worker itself. Write metadata to D1 and stream large blobs to R2.
- SendGrid retries the webhook POST on 5xx for up to 72 hours.
- Resend retries on 5xx for up to 3 days with exponential backoff.
- Both providers retry, so your handler must be idempotent on the `Message-ID` header.

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS inbound_emails (
  id            TEXT PRIMARY KEY,          -- normalised Message-ID
  received_at   TEXT NOT NULL,             -- ISO 8601
  provider      TEXT NOT NULL,             -- 'sendgrid' | 'resend'
  from_address  TEXT NOT NULL,
  to_address    TEXT NOT NULL,
  subject       TEXT,
  text_body     TEXT,
  html_body     TEXT,
  raw_headers   TEXT,                      -- JSON blob
  processed     INTEGER NOT NULL DEFAULT 0 -- 0 = pending, 1 = done
);

CREATE INDEX idx_inbound_from      ON inbound_emails(from_address);
CREATE INDEX idx_inbound_received  ON inbound_emails(received_at);
CREATE INDEX idx_inbound_processed ON inbound_emails(processed);
```

Apply with:

```bash
wrangler d1 execute YOUR_DB --file=./schema/inbound.sql
```

## Signature Verification

Never skip signature verification. Both providers sign their POSTs so you can reject
spoofed requests before any DB writes.

```typescript
// ── SendGrid: ECDSA P-256 signature ──────────────────────────────────────────
async function verifySendGrid(
  request: Request,
  rawBody: string,
  publicKey: string,          // base64-encoded DER SPKI from SendGrid dashboard
): Promise<boolean> {
  const signature = request.headers.get('X-Twilio-Email-Event-Webhook-Signature');
  const timestamp = request.headers.get('X-Twilio-Email-Event-Webhook-Timestamp');
  if (!signature || !timestamp) return false;

  const payload = timestamp + rawBody;
  const key = await crypto.subtle.importKey(
    'spki',
    base64ToBuffer(publicKey),
    { name: 'ECDSA', namedCurve: 'P-256' },
    false,
    ['verify'],
  );
  return crypto.subtle.verify(
    { name: 'ECDSA', hash: 'SHA-256' },
    key,
    base64ToBuffer(signature),
    new TextEncoder().encode(payload),
  );
}

// ── Resend: Svix-compatible HMAC-SHA256 ──────────────────────────────────────
async function verifyResend(
  request: Request,
  rawBody: string,
  webhookSecret: string,      // starts with 'whsec_'
): Promise<boolean> {
  const sig   = request.headers.get('svix-signature') ?? '';
  const ts    = request.headers.get('svix-timestamp') ?? '';
  const msgId = request.headers.get('svix-id') ?? '';
  const toSign = `${msgId}.${ts}.${rawBody}`;

  const secretBytes = base64ToBuffer(webhookSecret.replace(/^whsec_/, ''));
  const key = await crypto.subtle.importKey(
    'raw',
    secretBytes,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['verify'],
  );

  // Svix sends multiple signatures separated by spaces; any valid one passes
  for (const part of sig.split(' ')) {
    const v1 = part.startsWith('v1,') ? part.slice(3) : null;
    if (!v1) continue;
    const valid = await crypto.subtle.verify(
      'HMAC',
      key,
      base64ToBuffer(v1),
      new TextEncoder().encode(toSign),
    );
    if (valid) return true;
  }
  return false;
}

function base64ToBuffer(b64: string): ArrayBuffer {
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return buf.buffer;
}
```

## Parsing SendGrid Inbound Parse Payload

SendGrid sends `multipart/form-data`. Workers parse it with the native
`Request.formData()`.

```typescript
interface ParsedInbound {
  messageId: string;
  from: string;
  to: string;
  subject: string;
  text: string;
  html: string;
  headers: Record<string, string>;
}

async function parseSendGrid(request: Request): Promise<ParsedInbound> {
  const form = await request.formData();

  const rawHeaders = (form.get('headers') as string) ?? '';
  const headerMap: Record<string, string> = {};
  for (const line of rawHeaders.split('\n')) {
    const idx = line.indexOf(':');
    if (idx > 0) {
      const k = line.slice(0, idx).trim().toLowerCase();
      const v = line.slice(idx + 1).trim();
      headerMap[k] = v;
    }
  }

  const messageId = normaliseMessageId(
    headerMap['message-id'] ?? crypto.randomUUID(),
  );

  return {
    messageId,
    from:    stripDisplayName(form.get('from')    as string ?? ''),
    to:      stripDisplayName(form.get('to')      as string ?? ''),
    subject: form.get('subject') as string ?? '',
    text:    form.get('text')    as string ?? '',
    html:    form.get('html')    as string ?? '',
    headers: headerMap,
  };
}

function normaliseMessageId(raw: string): string {
  // Strip angle brackets: <abc@domain.tld> -> abc@domain.tld
  return raw.trim().replace(/^<|>$/g, '');
}

function stripDisplayName(address: string): string {
  // "Alice Smith" <alice@example.com>  ->  alice@example.com
  const match = address.match(/<([^>]+)>/);
  return match ? match[1].trim() : address.trim();
}
```

## Parsing Resend Inbound Payload

Resend sends a JSON body. The email object is nested under `data`.

```typescript
interface ResendInboundEvent {
  type: 'email.received';
  data: {
    message_id: string;
    from: string;
    to: string[];
    subject: string;
    text?: string;
    html?: string;
    headers: Array<{ name: string; value: string }>;
  };
}

async function parseResend(request: Request): Promise<ParsedInbound> {
  const body = (await request.json()) as ResendInboundEvent;
  const d = body.data;

  const headerMap = Object.fromEntries(
    d.headers.map(h => [h.name.toLowerCase(), h.value]),
  );

  return {
    messageId: normaliseMessageId(d.message_id),
    from:      stripDisplayName(d.from),
    to:        d.to.map(stripDisplayName).join(', '),
    subject:   d.subject ?? '',
    text:      d.text ?? '',
    html:      d.html ?? '',
    headers:   headerMap,
  };
}
```

## Writing to D1 with Idempotency

Use `INSERT OR IGNORE` to safely handle retried webhook deliveries. The `id` primary
key constraint silently drops the duplicate row without erroring.

```typescript
const MAX_TEXT_BYTES = 64_000;   // D1 TEXT column practical ceiling
const MAX_HTML_BYTES = 128_000;

async function storeInbound(
  db: D1Database,
  provider: string,
  parsed: ParsedInbound,
): Promise<void> {
  await db
    .prepare(`
      INSERT OR IGNORE INTO inbound_emails
        (id, received_at, provider, from_address, to_address,
         subject, text_body, html_body, raw_headers, processed)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    `)
    .bind(
      parsed.messageId,
      new Date().toISOString(),
      provider,
      parsed.from,
      parsed.to,
      parsed.subject,
      parsed.text.slice(0, MAX_TEXT_BYTES),
      parsed.html.slice(0, MAX_HTML_BYTES),
      JSON.stringify(parsed.headers),
    )
    .run();
}
```

## Worker Entry Point

```typescript
export interface Env {
  DB:                    D1Database;
  SENDGRID_WEBHOOK_KEY:  string;   // base64 DER SPKI public key
  RESEND_WEBHOOK_SECRET: string;   // whsec_... from Resend dashboard
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const { pathname } = new URL(request.url);
    const provider =
      pathname.endsWith('/sendgrid') ? 'sendgrid'
      : pathname.endsWith('/resend') ? 'resend'
      : null;

    if (!provider) return new Response('Not Found', { status: 404 });

    // Read the body once as text; we need it for both verification and parsing
    const rawBody = await request.text();

    // Re-construct a readable request for form/JSON parsing
    const parseable = new Request(request.url, {
      method:  'POST',
      headers: request.headers,
      body:    rawBody,
    });

    const verified =
      provider === 'sendgrid'
        ? await verifySendGrid(request, rawBody, env.SENDGRID_WEBHOOK_KEY)
        : await verifyResend(request, rawBody, env.RESEND_WEBHOOK_SECRET);

    if (!verified) {
      // Log but do not expose details — attacker could use error info
      console.error('Webhook signature verification failed', { provider });
      return new Response('Unauthorized', { status: 401 });
    }

    const parsed =
      provider === 'sendgrid'
        ? await parseSendGrid(parseable)
        : await parseResend(parseable);

    await storeInbound(env.DB, provider, parsed);

    return new Response('OK', { status: 200 });
  },
};
```

## wrangler.toml

```toml
name = "inbound-email"
main = "src/worker.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding  = "DB"
database_name = "email-db"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[vars]
# Set secrets via: wrangler secret put SENDGRID_WEBHOOK_KEY
#                  wrangler secret put RESEND_WEBHOOK_SECRET
```

## Anti-patterns

- **Returning 500 on a duplicate Message-ID**: Triggers provider retry loops for up to 3
  days. Use `INSERT OR IGNORE` and always return `200` for already-processed messages.
- **Buffering attachment binaries in the Worker**: A crafted email with a 10 MB PDF
  attachment can exhaust the Worker's 128 MB heap. Store attachment metadata in D1 and
  stream the binary to R2 using a pre-signed upload URL.
- **Skipping signature verification**: Any attacker who discovers your endpoint URL can
  inject synthetic emails. Verify before any DB interaction.
- **Reading `request.body` twice**: The body stream is consumed on first read. Always
  call `request.text()` once and reconstruct a new `Request` for subsequent parsing.
- **Storing full HTML without a size cap**: A crafted 10 MB HTML body can exceed D1's
  effective row size and abort the transaction. Truncate before binding.

## Gotchas

- SendGrid Inbound Parse sends attachments as separate form fields (`attachment1`,
  `attachment2`, ...) with an `attachment-info` JSON field describing content types.
  Enable **Attachments** in the SendGrid Inbound Parse dashboard to receive them.
- The `to` field from SendGrid may contain display names (`"Alice" <alice@example.com>`).
  Strip with `stripDisplayName()` before storing or indexing.
- Resend inbound is tied to a specific inbound email domain configured in the Resend
  dashboard. Test webhook delivery using the Resend dashboard's **Send test** button, not
  raw `curl` — the test request includes valid Svix signatures.
- D1 free tier is capped at 100 k write rows per day across all databases. Monitor
  `d1_rows_written` in Workers Analytics if you expect high inbound volume.
- Thread correlation: use the `In-Reply-To` and `References` headers (both present in
  `raw_headers`) to group replies into threads. Do not rely on `subject` alone.

## Verification

```bash
# 1. Deploy
wrangler deploy

# 2. Simulate a SendGrid Inbound Parse POST (no real signature — set SENDGRID_WEBHOOK_KEY='' for testing only)
curl -X POST https://inbound-email.your-subdomain.workers.dev/inbound/sendgrid \
  -F "from=alice@example.com" \
  -F "to=support@yourapp.com" \
  -F "subject=Test inbound" \
  -F "text=Hello from curl" \
  -F "html=<p>Hello from curl</p>" \
  -F "headers=Message-ID: <test-001@example.com>"

# 3. Confirm the row exists in D1
wrangler d1 execute YOUR_DB \
  --command "SELECT id, from_address, subject, processed FROM inbound_emails ORDER BY received_at DESC LIMIT 5"

# 4. Re-send the identical request — must return 200 with no duplicate row
# Confirm: row count for id='test-001@example.com' is still 1
wrangler d1 execute YOUR_DB \
  --command "SELECT COUNT(*) AS c FROM inbound_emails WHERE id='test-001@example.com'"
```

## Related

- `bounce-suppression-d1` — D1 write patterns for email infrastructure
- `transactional-queue-cloudflare-queues` — fan-out to async processors after the 200 response
- `email-webhook-idempotency-deduplication` — deduplication strategies beyond INSERT OR IGNORE
- `email-to-ticket-pattern` — joining inbound rows to support ticket records
- `cloudflare-email-routing-workers` — receiving SMTP mail via Email Routing instead of HTTP webhooks
- `email-parsing-patterns` — MIME parsing and thread correlation

## Sources

- [SendGrid Inbound Parse webhook docs](https://docs.sendgrid.com/for-developers/parsing-email/setting-up-the-inbound-parse-webhook)
- [Resend inbound webhooks](https://resend.com/docs/dashboard/webhooks/introduction)
- [Svix webhook verification](https://docs.svix.com/receiving/verifying-payloads/how)
- [Cloudflare D1 documentation](https://developers.cloudflare.com/d1/)
- [Workers Web Crypto API](https://developers.cloudflare.com/workers/runtime-apis/web-crypto/)
