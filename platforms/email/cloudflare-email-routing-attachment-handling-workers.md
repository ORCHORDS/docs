# Cloudflare Email Routing Attachment Handling in Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You have an Email Routing Worker that receives inbound email and needs to:

- Detect whether the message contains attachments
- Extract attachment metadata (filename, MIME type, size)
- Stream attachment bytes to R2 for storage or downstream processing
- Reject oversized or disallowed file types before forwarding

Without attachment-aware parsing the Worker forwards raw MIME blobs blindly or stores opaque byte strings in D1 where they do not belong.

---

## Context

Cloudflare Email Routing Workers receive a raw MIME message stream through the `email` handler's `EmailMessage.raw` `ReadableStream`. Attachments are encoded as `multipart/mixed` or `multipart/related` MIME parts, typically Base64-encoded.

The Workers runtime does not ship a native MIME parser. You must either:

1. Stream the raw message to a minimal hand-written boundary splitter, or
2. Use the `postal-mime` npm-compatible library (CJS-compatible, no Node built-ins required) bundled via Wrangler.

The 10 MB message size cap imposed by Email Routing applies to the entire raw message; individual attachment handling must account for Base64 overhead (~33 % inflation).

---

## Parsing Multipart Boundaries

```typescript
import PostalMime from "postal-mime";
import type { EmailMessage } from "cloudflare:email";

export default {
  async email(message: EmailMessage, env: Env, ctx: ExecutionContext) {
    // Consume the raw stream into an ArrayBuffer (≤10 MB Email Routing limit)
    const rawBuffer = await new Response(message.raw).arrayBuffer();

    const parser = new PostalMime();
    const parsed = await parser.parse(rawBuffer);

    if (!parsed.attachments || parsed.attachments.length === 0) {
      // No attachments — forward as normal
      await message.forward("support@internal.example.com");
      return;
    }

    ctx.waitUntil(
      handleAttachments(parsed.attachments, message, env)
    );

    // Forward stripped message (body only) or original
    await message.forward("support@internal.example.com");
  },
};
```

---

## Validating Attachment Type and Size

```typescript
const ALLOWED_MIME_TYPES = new Set([
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/gif",
  "text/plain",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024; // 5 MB per attachment

interface ParsedAttachment {
  filename?: string;
  mimeType: string;
  content: ArrayBuffer | Uint8Array;
  disposition?: string;
}

function validateAttachment(att: ParsedAttachment): string | null {
  const size =
    att.content instanceof ArrayBuffer
      ? att.content.byteLength
      : att.content.length;

  if (size > MAX_ATTACHMENT_BYTES) {
    return `Attachment "${att.filename}" exceeds ${MAX_ATTACHMENT_BYTES / 1e6} MB`;
  }

  if (!ALLOWED_MIME_TYPES.has(att.mimeType)) {
    return `MIME type "${att.mimeType}" is not permitted`;
  }

  return null; // valid
}
```

---

## Streaming Attachments to R2

```typescript
async function handleAttachments(
  attachments: ParsedAttachment[],
  message: EmailMessage,
  env: Env
) {
  const messageId = (message.headers.get("Message-ID") ?? crypto.randomUUID())
    .replace(/[<>]/g, "");

  for (const att of attachments) {
    const validationError = validateAttachment(att);
    if (validationError) {
      console.warn("Rejected attachment:", validationError);
      continue;
    }

    const filename = att.filename ?? `attachment-${crypto.randomUUID()}`;
    const key = `email-attachments/${messageId}/${filename}`;

    await env.ATTACHMENTS_BUCKET.put(key, att.content, {
      httpMetadata: {
        contentType: att.mimeType,
        contentDisposition: `attachment; filename="${filename}"`,
      },
      customMetadata: {
        sourceEmail: message.from,
        receivedAt: new Date().toISOString(),
        originalFilename: filename,
      },
    });

    // Record in D1 for retrieval
    await env.DB.prepare(
      `INSERT INTO email_attachments
         (message_id, r2_key, filename, mime_type, size_bytes, received_at)
       VALUES (?, ?, ?, ?, ?, datetime('now'))`
    )
      .bind(
        messageId,
        key,
        filename,
        att.mimeType,
        att.content instanceof ArrayBuffer
          ? att.content.byteLength
          : att.content.length
      )
      .run();
  }
}
```

---

## D1 Schema for Attachment Metadata

```sql
CREATE TABLE IF NOT EXISTS email_attachments (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id  TEXT NOT NULL,
  r2_key      TEXT NOT NULL UNIQUE,
  filename    TEXT NOT NULL,
  mime_type   TEXT NOT NULL,
  size_bytes  INTEGER NOT NULL,
  received_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_attachments_message
  ON email_attachments (message_id);
```

---

## Generating Presigned R2 Download URLs

```typescript
export async function createDownloadUrl(
  key: string,
  env: Env,
  expiresInSeconds = 3600
): Promise<string> {
  const url = await env.ATTACHMENTS_BUCKET.createPresignedUrl(key, {
    expiresIn: expiresInSeconds,
  });
  return url;
}
```

---

## Anti-patterns

- **Reading `message.raw` twice** — `ReadableStream` is single-use. Buffer into an `ArrayBuffer` once and pass that to the MIME parser.
- **Storing attachment bytes in D1** — D1 rows have a 1 MB value size limit and are not designed for binary blobs. Always use R2.
- **Trusting the `Content-Type` header alone** — validate by inspecting the file magic bytes (first 4–8 bytes) for executable signatures (e.g., `MZ` for PE, `#!` for scripts) in addition to MIME type checks.
- **Blocking the email handler on slow R2 puts** — use `ctx.waitUntil()` so the Worker ACKs Email Routing immediately.
- **Ignoring inline attachments** — `Content-Disposition: inline` parts (embedded images) should be handled separately from downloadable attachments (`attachment` disposition).

---

## Gotchas

- Email Routing enforces a **10 MB raw message size** cap. Messages exceeding this are bounced before the Worker fires.
- `postal-mime` decodes Base64 automatically; the returned `content` is already binary, not a Base64 string.
- Filenames in `Content-Disposition` may use RFC 2231 encoding (`filename*=UTF-8''...`). `postal-mime` handles this, but hand-rolled parsers often do not.
- R2 `put()` accepts `ArrayBuffer`, `ArrayBufferView`, `ReadableStream`, or `string`. Prefer `ArrayBuffer` for attachment bytes received from `postal-mime`.
- Workers bundled with `postal-mime` add ~150 KB to the compressed bundle; stay within the 3 MB Worker script size limit.

---

## Verification

```bash
# Install postal-mime
npm install postal-mime

# Deploy worker
wrangler deploy

# Send a test email with an attachment using swaks
swaks --to inbound@routing-domain.com \
  --attach-type application/pdf \
  --attach ./test.pdf \
  --body "Please find attached."

# Confirm R2 object was created
wrangler r2 object get ATTACHMENTS_BUCKET \
  "email-attachments/<message-id>/test.pdf" --file /tmp/verify.pdf

# Check D1 record
wrangler d1 execute DB \
  --command "SELECT * FROM email_attachments ORDER BY received_at DESC LIMIT 5"
```

---

## Related

- `email-attachment-scanning-r2-workers-ai.md`
- `email-attachment-patterns.md`
- `cloudflare-email-routing-workers.md`
- `inbound-email-processing.md`
- `email-content-html-sanitization-workers.md`

---

## Sources

- Cloudflare Email Routing Workers — https://developers.cloudflare.com/email-routing/email-workers/
- postal-mime library — https://github.com/postalsys/postal-mime
- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- RFC 2183 Content-Disposition — https://datatracker.ietf.org/doc/html/rfc2183
