# Multipart/Mixed MIME Parsing in Workers Email Handler

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
An inbound Workers Email handler receives multipart/mixed messages (HTML body + plain-text fallback + file attachments) and needs to split the parts, decode each one, and store attachments in R2 before forwarding a clean summary to D1.

## Context
Cloudflare Email Routing exposes `message.raw` as a `ReadableStream<Uint8Array>` and `message.headers` as an iterable.
There is no built-in MIME parser in the Workers runtime; `postal-mime` (npm) is the standard choice and bundles cleanly under Wrangler.
Attachments must be streamed to R2 rather than buffered in memory to stay within the 128 MB memory limit.

---

## Setup / Dependencies

```bash
npm install postal-mime
```

```typescript
// wrangler.toml (excerpt)
// r2_buckets = [{ binding = "ATTACHMENTS_R2", bucket_name = "email-attachments" }]
// d1_databases = [{ binding = "DB", database_name = "email-store", database_id = "..." }]

export interface Env {
  ATTACHMENTS_R2: R2Bucket;
  DB: D1Database;
  FORWARD_ADDRESS: string;
}
```

```sql
-- D1 schema
CREATE TABLE IF NOT EXISTS inbound_messages (
  id            TEXT PRIMARY KEY,   -- Message-ID stripped
  from_addr     TEXT NOT NULL,
  to_addr       TEXT NOT NULL,
  subject       TEXT NOT NULL,
  body_html     TEXT,
  body_text     TEXT,
  received_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS message_attachments (
  id            TEXT PRIMARY KEY,   -- random UUID
  message_id    TEXT NOT NULL REFERENCES inbound_messages(id),
  filename      TEXT,
  content_type  TEXT NOT NULL,
  size_bytes    INTEGER NOT NULL,
  r2_key        TEXT NOT NULL,
  FOREIGN KEY (message_id) REFERENCES inbound_messages(id)
);
```

## Email Handler — MIME Parsing and Extraction

```typescript
// src/email-handler.ts
import PostalMime from 'postal-mime';
import type { Email, Attachment } from 'postal-mime';
import { EmailMessage } from 'cloudflare:email';

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext): Promise<void> {
    // 1. Buffer the raw email stream — postal-mime requires ArrayBuffer
    //    Workers limit is 100 MB for email; postal-mime handles chunked reassembly
    const rawResponse = new Response(message.raw);
    const rawBuffer   = await rawResponse.arrayBuffer();

    // 2. Parse with postal-mime
    const parser = new PostalMime();
    let parsed: Email;
    try {
      parsed = await parser.parse(rawBuffer);
    } catch (err) {
      console.error('MIME parse error:', err);
      // Forward anyway to avoid losing mail
      await message.forward(env.FORWARD_ADDRESS);
      return;
    }

    const messageId = stripAngleBrackets(
      parsed.headers.find((h) => h.key === 'message-id')?.value ??
        `unknown-${crypto.randomUUID()}`
    );

    // 3. Persist message metadata to D1
    await env.DB.prepare(
      `INSERT OR IGNORE INTO inbound_messages
         (id, from_addr, to_addr, subject, body_html, body_text, received_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        messageId,
        parsed.from?.address ?? message.from,
        message.to,
        parsed.subject ?? '(no subject)',
        (parsed.html ?? '').slice(0, 65_000),
        (parsed.text ?? '').slice(0, 65_000),
        Math.floor(Date.now() / 1000)
      )
      .run();

    // 4. Store attachments in R2 and record metadata in D1
    if (parsed.attachments && parsed.attachments.length > 0) {
      const attachmentOps = parsed.attachments.map((att) =>
        storeAttachment(att, messageId, env)
      );
      // waitUntil so we don't block forward but ensure completion
      ctx.waitUntil(Promise.allSettled(attachmentOps));
    }

    // 5. Forward the original message
    await message.forward(env.FORWARD_ADDRESS);
  },
};

async function storeAttachment(
  att: Attachment,
  messageId: string,
  env: Env
): Promise<void> {
  const attachmentId = crypto.randomUUID();
  const safeFilename = sanitizeFilename(att.filename ?? `attachment-${attachmentId}`);
  const r2Key = `${messageId}/${attachmentId}/${safeFilename}`;

  // att.content is Uint8Array | ArrayBuffer depending on postal-mime version
  const body =
    att.content instanceof Uint8Array ? att.content : new Uint8Array(att.content as ArrayBuffer);

  await env.ATTACHMENTS_R2.put(r2Key, body, {
    httpMetadata: {
      contentType: att.mimeType ?? 'application/octet-stream',
      contentDisposition: `attachment; filename="${safeFilename}"`,
    },
    customMetadata: {
      messageId,
      originalFilename: att.filename ?? '',
    },
  });

  await env.DB.prepare(
    `INSERT INTO message_attachments
       (id, message_id, filename, content_type, size_bytes, r2_key)
     VALUES (?, ?, ?, ?, ?, ?)`
  )
    .bind(
      attachmentId,
      messageId,
      att.filename ?? null,
      att.mimeType ?? 'application/octet-stream',
      body.byteLength,
      r2Key
    )
    .run();
}
```

## Utility Functions

```typescript
function stripAngleBrackets(value: string): string {
  return value.replace(/^<|>$/g, '').trim();
}

function sanitizeFilename(name: string): string {
  // Remove path traversal and null bytes; keep only safe characters
  return name
    .replace(/\.\./g, '')
    .replace(/\//g, '-')
    .replace(/\x00/g, '')
    .replace(/[^\w.\-_() ]/g, '_')
    .slice(0, 255);
}
```

## Serving Attachments — Pre-Signed R2 Download

```typescript
// src/api-worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // GET /attachments/:attachmentId
    const match = url.pathname.match(/^\/attachments\/([a-f0-9-]{36})$/);
    if (!match) return new Response('Not Found', { status: 404 });

    const row = await env.DB.prepare(
      `SELECT r2_key, content_type, filename FROM message_attachments WHERE id = ?`
    )
      .bind(match[1])
      .first<{ r2_key: string; content_type: string; filename: string | null }>();

    if (!row) return new Response('Not Found', { status: 404 });

    // Stream directly from R2
    const obj = await env.ATTACHMENTS_R2.get(row.r2_key);
    if (!obj) return new Response('Not Found in R2', { status: 404 });

    return new Response(obj.body, {
      headers: {
        'Content-Type': row.content_type,
        'Content-Disposition': `attachment; filename="${row.filename ?? 'file'}"`,
        'Cache-Control': 'private, max-age=3600',
      },
    });
  },
};
```

## Anti-patterns
- Calling `new Response(message.raw).text()` — this decodes as UTF-8 and corrupts binary attachments (images, PDFs); always use `.arrayBuffer()`.
- Awaiting `storeAttachment` inside the `email()` handler — large attachments can exhaust the 30-second CPU limit; use `ctx.waitUntil` for background I/O.
- Storing the full raw email in D1 — D1 rows have a 1 MB practical limit; store only text bodies and push binary content to R2.
- Trusting `att.filename` without sanitization — MIME filenames can contain path traversal (`../../etc/passwd`); always sanitize before using as R2 keys.
- Parsing MIME manually with string splitting — boundary parameters can contain quotes, whitespace, and escaped characters; use a proper parser.

## Gotchas
- `postal-mime` v2.x returns `att.content` as `Uint8Array`; v1.x returns `ArrayBuffer` — check the version and normalise.
- The Workers Email handler must call either `message.forward()`, `message.reply()`, or `message.setReject()` — not calling any results in the email being dropped silently.
- `postal-mime` bundles cleanly with `wrangler build` but requires `nodejs_compat = true` in `wrangler.toml` because it uses Node.js `Buffer` internally.
- Embedded inline images with `Content-Disposition: inline` and `Content-ID` headers are included in `parsed.attachments` — filter by `att.disposition !== 'inline'` if you only want file attachments.
- R2 PUT is limited to 5 GB per object; email attachments rarely exceed this, but if scanning large objects add a size gate before upload.

## Verification

```bash
# Check messages are stored
wrangler d1 execute email-store \
  --command "SELECT id, from_addr, subject FROM inbound_messages ORDER BY received_at DESC LIMIT 5" \
  --remote

# Check attachments table
wrangler d1 execute email-store \
  --command "SELECT a.filename, a.content_type, a.size_bytes, a.r2_key FROM message_attachments a ORDER BY rowid DESC LIMIT 10" \
  --remote

# Verify R2 objects exist
wrangler r2 object list email-attachments --remote --limit 10
```

## Related
- `multipart-mime-structure.md` — MIME RFC concepts and part hierarchy
- `email-attachment-patterns.md` — attachment handling strategies
- `email-attachment-scanning-r2-workers-ai.md` — AI-based scanning before storage
- `email-attachment-virus-scan-r2-workers.md` — VirusTotal scanning of R2-stored attachments
- `cloudflare-email-routing-attachment-handling-workers.md` — routing rules for large attachments

## Sources
- https://developers.cloudflare.com/email-routing/email-workers/
- https://github.com/postalsys/postal-mime
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/d1/
- https://datatracker.ietf.org/doc/html/rfc2045 (MIME Part One)
- https://datatracker.ietf.org/doc/html/rfc2183 (Content-Disposition)
