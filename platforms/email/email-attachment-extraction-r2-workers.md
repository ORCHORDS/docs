# Email Attachment Extraction and R2 Storage with Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Inbound emails delivered to a Cloudflare Email Worker contain binary attachments (PDFs, images, spreadsheets) that need to be stored durably and made available via download URLs. Parsing raw MIME inside a Worker and streaming each attachment directly to R2 eliminates the need for a third-party mail-processing service.

---

## Context

Cloudflare Email Workers receive an `EmailMessage` object whose `raw` property is a `ReadableStream` of the full RFC 2822 message. The `postal-mime` library (available as an npm package) parses that stream into a structured object including a `parsed.attachments` array. Each attachment carries its filename, MIME type, and content as an `ArrayBuffer`. Writing each buffer to R2 with a deterministic key and recording the metadata in D1 keeps the system fully within the Cloudflare stack. A signed, time-limited download URL is generated using the R2 `createPresignedUrl` approach or by routing through a Worker that enforces auth.

---

## Section 1 — wrangler.toml / Schema

```toml
name = "email-attachment-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[vars]
ATTACHMENT_URL_TTL_SECONDS = "3600"

[[email]]
name = "INBOUND_EMAIL"

[[r2_buckets]]
binding = "ATTACHMENTS"
bucket_name = "email-attachments"

[[d1_databases]]
binding = "DB"
database_name = "email-db"
database_id = "YOUR_D1_DATABASE_ID"
```

```sql
CREATE TABLE IF NOT EXISTS email_attachments (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id  TEXT    NOT NULL,
  filename    TEXT    NOT NULL,
  content_type TEXT   NOT NULL,
  size_bytes  INTEGER NOT NULL,
  r2_key      TEXT    NOT NULL UNIQUE,
  created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_attachments_message ON email_attachments(message_id);
```

## Section 2 — Worker implementation

```typescript
import PostalMime from 'postal-mime';

export interface Env {
  ATTACHMENTS: R2Bucket;
  DB: D1Database;
  ATTACHMENT_URL_TTL_SECONDS: string;
}

function generateR2Key(messageId: string, filename: string, index: number): string {
  const safeFilename = filename.replace(/[^a-zA-Z0-9._-]/g, '_');
  return `attachments/${messageId}/${index}-${safeFilename}`;
}

async function streamToArrayBuffer(stream: ReadableStream<Uint8Array>): Promise<ArrayBuffer> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) chunks.push(value);
  }
  const total = chunks.reduce((n, c) => n + c.byteLength, 0);
  const buffer = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    buffer.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return buffer.buffer;
}

export default {
  async email(message: EmailMessage, env: Env, _ctx: ExecutionContext): Promise<void> {
    const rawBuffer = await streamToArrayBuffer(message.raw);
    const parser = new PostalMime();
    const parsed = await parser.parse(rawBuffer);

    const messageId =
      (parsed.messageId ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`).replace(
        /[<>]/g,
        ''
      );

    if (!parsed.attachments || parsed.attachments.length === 0) {
      console.log(`Message ${messageId} has no attachments.`);
      return;
    }

    const insertStmt = env.DB.prepare(
      `INSERT OR IGNORE INTO email_attachments
         (message_id, filename, content_type, size_bytes, r2_key)
       VALUES (?, ?, ?, ?, ?)`
    );

    for (let i = 0; i < parsed.attachments.length; i++) {
      const att = parsed.attachments[i];
      const filename = att.filename ?? `attachment-${i}`;
      const contentType = att.mimeType ?? 'application/octet-stream';
      const r2Key = generateR2Key(messageId, filename, i);

      // Upload to R2
      await env.ATTACHMENTS.put(r2Key, att.content, {
        httpMetadata: { contentType },
        customMetadata: { messageId, filename },
      });

      // Record metadata in D1
      await insertStmt
        .bind(messageId, filename, contentType, att.content.byteLength, r2Key)
        .run();

      console.log(`Stored attachment: ${r2Key} (${att.content.byteLength} bytes)`);
    }
  },
};
```

## Section 3 — Download URL handler

```typescript
// Separate Worker or additional fetch handler for generating signed download links
export async function handleDownloadRequest(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const r2Key = url.searchParams.get('key');
  if (!r2Key) return new Response('Missing key', { status: 400 });

  // Auth check omitted — integrate your JWT/session logic here

  const object = await env.ATTACHMENTS.get(r2Key);
  if (!object) return new Response('Not found', { status: 404 });

  const contentType =
    object.httpMetadata?.contentType ?? 'application/octet-stream';
  const filename =
    object.customMetadata?.filename ?? r2Key.split('/').pop() ?? 'download';

  return new Response(object.body, {
    headers: {
      'Content-Type': contentType,
      'Content-Disposition': `attachment; filename="${filename}"`,
      'Cache-Control': 'private, max-age=3600',
    },
  });
}
```

---

## Anti-patterns

- **Storing attachment bytes in D1** — D1 is a relational SQL store; binary blobs belong in R2. Storing large BLOBs in D1 will hit row-size limits and degrade query performance.
- **Parsing the raw stream twice** — `message.raw` is a one-time `ReadableStream`; tee it if you need to process the body more than once, or buffer it upfront as shown.
- **Using the email subject as the R2 key** — Subjects are user-controlled, may contain special characters, and are not unique. Always derive keys from the message-ID and an index.
- **Ignoring `content.byteLength === 0`** — Some MIME parts are empty placeholder attachments. Skip them to avoid writing zero-byte objects to R2.

---

## Gotchas

- `postal-mime` must be listed as a dependency in `package.json` and bundled with the Worker; it is not a built-in Cloudflare runtime module.
- Email Workers do not have a `fetch` handler — the entrypoint is the `email` method on the default export object.
- R2 key names are case-sensitive. Normalise filenames to lowercase if you need case-insensitive lookups.
- D1 `INSERT OR IGNORE` silently drops duplicate inserts; use `INSERT OR REPLACE` if you want to update existing attachment records on redelivery.
- The `message.raw` stream is only readable once per invocation. Buffer it before passing to the parser.

---

## Verification

```bash
# Deploy the Worker
npx wrangler deploy

# Send a test email with an attachment via curl + SMTP relay or swaks
swaks --to test@yourdomain.com \
      --from sender@example.com \
      --attach-type application/pdf \
      --attach ./sample.pdf \
      --body "Test attachment"

# Confirm the R2 object was created
npx wrangler r2 object get email-attachments attachments/<message-id>/0-sample.pdf --file /tmp/out.pdf

# Confirm D1 metadata row
npx wrangler d1 execute email-db \
  --command "SELECT * FROM email_attachments ORDER BY created_at DESC LIMIT 5;"
```

---

## Related

- `email-bounce-webhook-mailchannels-d1.md`
- `email-template-rendering-workers-r2.md`

---

## Sources

- Cloudflare Email Workers — https://developers.cloudflare.com/email-routing/email-workers/
- PostalMime npm — https://www.npmjs.com/package/postal-mime
- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- Cloudflare D1 Workers API — https://developers.cloudflare.com/d1/worker-api/
