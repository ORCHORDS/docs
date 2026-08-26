# Inbound Email Parsing with Email Routing Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to process inbound emails programmatically — parse headers, extract plain text and HTML body, handle MIME multipart messages with attachments, store attachments in R2, route different addresses to different handlers, send auto-replies, and reject obvious spam. Cloudflare Email Routing lets you forward inbound mail to a Worker, but the raw `EmailMessage` API requires careful handling of MIME multipart structures that most guides skip.

---

## Context

Cloudflare Email Routing Workers receive inbound emails via the `email` handler (parallel to `fetch` and `queue`). The `EmailMessage` object exposes `from`, `to`, `headers`, and a `raw` `ReadableStream` of the RFC 5322 message. There is no built-in MIME parser — you must parse the raw stream yourself or stream it to a downstream processor. R2 stores attachments. D1 stores a parsed-message index. The spam score is available via the `X-Spam-Score` header injected by Cloudflare's spam filter.

Prerequisites:
- Email Routing enabled on the Cloudflare zone
- Worker bound to receive email for `*@inbound.example.com`
- R2 bucket bound as `ATTACHMENTS`
- D1 database bound as `DB`
- Queue bound as `REPLY_QUEUE` for async auto-replies

---

## Solution

```typescript
// wrangler.toml (excerpt)
// [triggers]
// email_routing = [
//   { pattern = "*@inbound.example.com" }
// ]
//
// [[r2_buckets]]
// binding = "ATTACHMENTS"
// bucket_name = "email-attachments-prod"

export interface Env {
  ATTACHMENTS: R2Bucket;
  DB: D1Database;
  REPLY_QUEUE: Queue<AutoReplyJob>;
  SPAM_SCORE_THRESHOLD: string; // e.g. "5.0"
  SUPPORT_ADDRESS: string;      // e.g. "support@example.com"
}

// ── D1 schema ─────────────────────────────────────────────────────────────────
// CREATE TABLE IF NOT EXISTS inbound_emails (
//   id              TEXT PRIMARY KEY,
//   from_address    TEXT NOT NULL,
//   to_address      TEXT NOT NULL,
//   subject         TEXT,
//   spam_score      REAL,
//   body_text       TEXT,
//   received_at     TEXT NOT NULL,
//   handler         TEXT NOT NULL,
//   attachment_count INTEGER NOT NULL DEFAULT 0
// );
// CREATE TABLE IF NOT EXISTS inbound_attachments (
//   id         TEXT PRIMARY KEY,
//   email_id   TEXT NOT NULL REFERENCES inbound_emails(id),
//   filename   TEXT,
//   mime_type  TEXT,
//   size_bytes INTEGER,
//   r2_key     TEXT NOT NULL
// );

interface ParsedMimePart {
  headers: Record<string, string>;
  contentType: string;
  isAttachment: boolean;
  filename: string | null;
  body: Uint8Array;
}

interface AutoReplyJob {
  to: string;
  from: string;
  subject: string;
  textBody: string;
}

// ── Minimal MIME multipart parser ─────────────────────────────────────────────
// Handles flat multipart/mixed and multipart/alternative. Not a full RFC 2822
// parser — handles the 95% case for typical email attachments.
function parseMimeMultipart(raw: string, boundary: string): ParsedMimePart[] {
  const delimiter = `--${boundary}`;
  const parts: ParsedMimePart[] = [];

  // Split on boundary markers; first and last segments are preamble/epilogue
  const segments = raw.split(new RegExp(`\r?\n${delimiter.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:--)?(\r?\n|$)`));

  for (const segment of segments) {
    if (!segment.trim()) continue;

    // Split headers from body on double CRLF
    const headerBodySplit = segment.indexOf('\r\n\r\n') !== -1
      ? segment.indexOf('\r\n\r\n')
      : segment.indexOf('\n\n');
    if (headerBodySplit === -1) continue;

    const headerBlock = segment.slice(0, headerBodySplit);
    const bodyBlock = segment.slice(headerBodySplit + (segment[headerBodySplit + 2] === '\n' ? 2 : 4));

    // Parse header lines
    const headers: Record<string, string> = {};
    for (const line of headerBlock.split(/\r?\n/)) {
      const colon = line.indexOf(':');
      if (colon === -1) continue;
      const key = line.slice(0, colon).trim().toLowerCase();
      const value = line.slice(colon + 1).trim();
      headers[key] = value;
    }

    const contentType = headers['content-type'] ?? 'application/octet-stream';
    const disposition = headers['content-disposition'] ?? '';
    const isAttachment = disposition.startsWith('attachment') || disposition.startsWith('inline;');

    // Extract filename from Content-Disposition or Content-Type
    let filename: string | null = null;
    const filenameMatch = disposition.match(/filename\*?=["']?([^"'\s;]+)["']?/i)
      ?? contentType.match(/name=["']?([^"'\s;]+)["']?/i);
    if (filenameMatch) filename = filenameMatch[1].replace(/^utf-8''/i, '');

    // Decode body
    const encoding = (headers['content-transfer-encoding'] ?? '').toLowerCase();
    let bodyBytes: Uint8Array;
    if (encoding === 'base64') {
      const stripped = bodyBlock.replace(/\s/g, '');
      bodyBytes = Uint8Array.from(atob(stripped), (c) => c.charCodeAt(0));
    } else if (encoding === 'quoted-printable') {
      const decoded = bodyBlock
        .replace(/=\r?\n/g, '') // soft line breaks
        .replace(/=([0-9A-Fa-f]{2})/g, (_, h) => String.fromCharCode(parseInt(h, 16)));
      bodyBytes = new TextEncoder().encode(decoded);
    } else {
      bodyBytes = new TextEncoder().encode(bodyBlock);
    }

    parts.push({ headers, contentType, isAttachment, filename, body: bodyBytes });
  }

  return parts;
}

// ── Extract boundary from Content-Type header ─────────────────────────────────
function extractBoundary(contentType: string): string | null {
  const m = contentType.match(/boundary=["']?([^"'\s;]+)["']?/i);
  return m ? m[1] : null;
}

// ── Extract plain-text body (best-effort) ─────────────────────────────────────
function extractTextBody(raw: string, contentType: string): string {
  if (!contentType.startsWith('multipart/')) {
    // Single-part message — body follows double newline
    const split = raw.indexOf('\r\n\r\n');
    return split !== -1 ? raw.slice(split + 4) : raw;
  }
  const boundary = extractBoundary(contentType);
  if (!boundary) return '';
  const parts = parseMimeMultipart(raw, boundary);
  const textPart = parts.find(
    (p) => p.contentType.startsWith('text/plain') && !p.isAttachment
  );
  return textPart ? new TextDecoder().decode(textPart.body) : '';
}

// ── Spam score extraction ─────────────────────────────────────────────────────
function spamScore(headers: Headers): number {
  const raw = headers.get('x-spam-score') ?? headers.get('x-spam-status');
  if (!raw) return 0;
  const m = raw.match(/([\d.]+)/);
  return m ? parseFloat(m[1]) : 0;
}

// ── Address-pattern routing ───────────────────────────────────────────────────
type Handler = 'support' | 'billing' | 'careers' | 'default';

function routeByAddress(to: string): Handler {
  const local = to.split('@')[0].toLowerCase();
  if (local === 'support' || local.startsWith('ticket-')) return 'support';
  if (local === 'billing' || local === 'invoices') return 'billing';
  if (local === 'careers' || local === 'jobs') return 'careers';
  return 'default';
}

// ── Auto-reply helper ─────────────────────────────────────────────────────────
async function enqueueAutoReply(
  queue: Queue<AutoReplyJob>,
  to: string,
  from: string,
  originalSubject: string
): Promise<void> {
  const subject = originalSubject.startsWith('Re:')
    ? originalSubject
    : `Re: ${originalSubject}`;
  await queue.send({
    to,
    from,
    subject,
    textBody:
      'Thank you for contacting Orchords. We have received your message and ' +
      'will respond within one business day.\n\nOrchords Support Team',
  });
}

// ── Store attachments to R2 ───────────────────────────────────────────────────
async function storeAttachments(
  bucket: R2Bucket,
  db: D1Database,
  emailId: string,
  parts: ParsedMimePart[]
): Promise<number> {
  const attachments = parts.filter((p) => p.isAttachment && p.body.length > 0);
  if (!attachments.length) return 0;

  const stmts = [];
  for (const part of attachments) {
    const attachId = crypto.randomUUID();
    const ext = (part.filename ?? 'file').split('.').pop() ?? 'bin';
    const r2Key = `attachments/${emailId}/${attachId}.${ext}`;

    await bucket.put(r2Key, part.body, {
      httpMetadata: {
        contentType: part.contentType.split(';')[0].trim(),
        contentDisposition: part.filename
          ? `attachment; filename="${part.filename}"`
          : 'attachment',
      },
      customMetadata: {
        email_id: emailId,
        original_filename: part.filename ?? '',
      },
    });

    stmts.push(
      db
        .prepare(
          `INSERT INTO inbound_attachments (id, email_id, filename, mime_type, size_bytes, r2_key)
           VALUES (?, ?, ?, ?, ?, ?)`
        )
        .bind(
          attachId,
          emailId,
          part.filename ?? null,
          part.contentType.split(';')[0].trim(),
          part.body.length,
          r2Key
        )
    );
  }

  await db.batch(stmts);
  return attachments.length;
}

// ── Email handler ─────────────────────────────────────────────────────────────
export default {
  async email(message: ForwardableEmailMessage, env: Env, ctx: ExecutionContext): Promise<void> {
    // 1. Spam check
    const score = spamScore(message.headers);
    const threshold = parseFloat(env.SPAM_SCORE_THRESHOLD);
    if (score >= threshold) {
      // Reject with a 5xx so the sending MTA knows it was refused
      message.setReject(`Spam score ${score} exceeds threshold ${threshold}`);
      return;
    }

    // 2. Read raw message
    const rawBytes = await new Response(message.raw).arrayBuffer();
    const rawText = new TextDecoder('utf-8', { fatal: false }).decode(rawBytes);

    // 3. Extract key fields
    const from = message.from;
    const to = message.to;
    const subject = message.headers.get('subject') ?? '(no subject)';
    const contentType = message.headers.get('content-type') ?? 'text/plain';

    // 4. Parse MIME parts
    let parts: ParsedMimePart[] = [];
    if (contentType.startsWith('multipart/')) {
      const boundary = extractBoundary(contentType);
      if (boundary) parts = parseMimeMultipart(rawText, boundary);
    }

    // 5. Extract plain-text body
    const textBody = extractTextBody(rawText, contentType).slice(0, 4096); // cap for D1 storage

    // 6. Route to handler
    const handler = routeByAddress(to);

    // 7. Store email record in D1
    const emailId = crypto.randomUUID();
    const receivedAt = new Date().toISOString();

    await env.DB
      .prepare(
        `INSERT INTO inbound_emails
           (id, from_address, to_address, subject, spam_score, body_text, received_at, handler)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .bind(emailId, from, to, subject, score, textBody, receivedAt, handler)
      .run();

    // 8. Store attachments in R2 + D1 (waitUntil for large payloads)
    const attachmentCount = await storeAttachments(
      env.ATTACHMENTS, env.DB, emailId, parts
    );

    if (attachmentCount > 0) {
      await env.DB
        .prepare('UPDATE inbound_emails SET attachment_count = ? WHERE id = ?')
        .bind(attachmentCount, emailId)
        .run();
    }

    // 9. Handler-specific logic
    if (handler === 'support' || handler === 'default') {
      ctx.waitUntil(
        enqueueAutoReply(env.REPLY_QUEUE, from, env.SUPPORT_ADDRESS, subject)
      );
    }

    // 10. Forward to internal destination for handlers that need it
    if (handler === 'billing') {
      await message.forward('billing-team@example.com');
    }
  },
};
```

---

## Implementation Details

- **`ForwardableEmailMessage`**: the `email` handler receives a `ForwardableEmailMessage` which extends `EmailMessage` with `forward(rcpt)`, `reply(response)`, and `setReject(reason)`. The `raw` property is a `ReadableStream<Uint8Array>` of the full RFC 5322 message including headers.
- **MIME parser scope**: the inline parser handles `multipart/mixed`, `multipart/alternative`, and `multipart/related` at one level of nesting. Deeply nested MIME (e.g. a `multipart/mixed` containing a `multipart/alternative`) requires a recursive descent; for production use consider streaming to a Durable Object or a dedicated MIME parsing Worker with more CPU budget.
- **Spam scoring**: Cloudflare injects `X-Spam-Score` and `X-Spam-Status` headers before the Worker receives the message. Scores above 5.0 are typically considered spam; tune the threshold based on your false-positive rate.
- **`message.setReject`**: calling this stops processing and sends a 5xx SMTP rejection back to the sender's MTA. Use it only for clear spam — legitimate senders will not retry after a permanent 5xx.
- **R2 attachment keys**: using `emailId/attachmentId.ext` as the key provides natural grouping. Lifecycle rules can be set on the bucket to delete attachments older than N days.
- **`ctx.waitUntil`**: auto-reply queue sends should use `waitUntil` to avoid blocking the email handler — the email handler has a shorter deadline than a standard fetch handler.

---

## Anti-patterns

- **Reading `message.raw` twice** — `ReadableStream` can only be consumed once. Read it into an `ArrayBuffer` immediately and derive all representations from that.
- **Storing full raw email in D1** — raw emails with attachments can be megabytes. Store only the parsed text body (capped) and metadata in D1; put binary content in R2.
- **Calling `message.forward` after `setReject`** — the Email Routing runtime only allows one terminal action per message. After `setReject`, any subsequent `forward` or `reply` call is a no-op or throws.
- **Parsing MIME with a simple `split('\n\n')`** — email bodies may contain literal double newlines in quoted text. Always split on the first double newline after the header block only.
- **Trusting `From` header without DKIM verification** — Cloudflare Email Routing performs DKIM/SPF/DMARC checks and exposes results via `X-Email-Authentication-Results`. Check this header before taking action on the claimed sender identity.

---

## Gotchas

- The `email` export must be at the top level of the Worker's default export object alongside `fetch`. If only `fetch` is exported, the Worker will not receive email events.
- `message.headers` is a read-only `Headers` object. You cannot add or modify headers before forwarding; forwarded messages carry the original headers.
- `base64` decoding with `atob` fails on strings containing whitespace. Always strip whitespace from base64-encoded MIME part bodies before decoding.
- Email Routing Workers have a 10 MB message size limit. Emails with large attachments above this limit are rejected before reaching the Worker — inform senders via your MX SMTP banner.
- `quoted-printable` encoding uses `=XX` hex escapes and `=\n` soft line breaks. The soft line break `=` at end of line must be removed before decoding hex sequences, as shown in `parseMimeMultipart`.
- The `wrangler.toml` `[triggers]` block for Email Routing Workers uses `email_routing` key; this differs from the `crons` or `queues` keys and requires Cloudflare Email Routing to be enabled on the zone separately.

---

## Verification

```bash
# Send a test email with attachment using curl + sendmail syntax
echo 'Subject: Test\nFrom: test@example.com\n\nHello' | \
  curl -v smtp://localhost:25 --mail-from test@example.com \
       --mail-rcpt support@inbound.example.com --upload-file -

# Or use swaks (Swiss Army Knife SMTP)
swaks --to support@inbound.example.com \
      --from sender@example.com \
      --attach /path/to/file.pdf \
      --server mx.example.com

# Verify record in D1
wrangler d1 execute email-db --command \
  "SELECT id, from_address, subject, handler, attachment_count, spam_score
   FROM inbound_emails ORDER BY received_at DESC LIMIT 5;"

# List attachments stored in R2
wrangler r2 object list email-attachments-prod --prefix attachments/

# Tail live email handler logs
wrangler tail --format pretty
```

---

## Related

- `workers-transactional-email-queue.md` — sending auto-replies via the queue consumer
- `workers-email-unsubscribe-manager.md` — honouring unsubscribe requests received via inbound email
- Cloudflare Email Routing Workers: https://developers.cloudflare.com/email-routing/email-workers/

---

## Sources

- https://developers.cloudflare.com/email-routing/email-workers/runtime-api/
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://www.rfc-editor.org/rfc/rfc2045 (MIME Part One)
- https://www.rfc-editor.org/rfc/rfc2822 (Internet Message Format)
