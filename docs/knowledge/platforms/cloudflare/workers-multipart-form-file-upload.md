# workers-multipart-form-file-upload

Parse multipart form data and handle binary file uploads in Workers — reading
fields, extracting file bytes, validating MIME types, and persisting to R2
without loading the entire body into memory.

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

## Symptom / Use-case

Your Worker needs to accept file uploads from browsers or API clients:

- A form that submits `<input type="file">` alongside text fields
- A mobile app posting images as `multipart/form-data`
- A CSV or JSON upload pipeline where the file goes to R2 and metadata to D1
- Generating a presigned R2 URL was too complex; a direct upload Worker is simpler

## Context

Workers expose the Web standard `Request.formData()` API which parses
`multipart/form-data` and `application/x-www-form-urlencoded` bodies. For file
parts, `formData.get("file")` returns a `File` object (a `Blob` subclass) with
`.name`, `.type`, `.size`, and `.arrayBuffer()` / `.stream()` methods.

The entire body is buffered in memory when you call `request.formData()`. For
large files (>100 MB) this can exceed the Worker memory limit (128 MB default,
512 MB on Unbound). For very large files, use R2 presigned URLs or the R2
multipart upload API directly; for typical uploads (<50 MB), `formData()` is
correct and simple.

## Reading form fields and a single file

```typescript
export interface Env {
  UPLOADS: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const contentType = request.headers.get("Content-Type") ?? "";
    if (!contentType.includes("multipart/form-data")) {
      return new Response("Expected multipart/form-data", { status: 415 });
    }

    // Buffers the entire body — fine for files < 50 MB
    const form = await request.formData();

    const title = form.get("title");
    const file = form.get("file");

    if (typeof title !== "string" || !title.trim()) {
      return new Response("Missing title field", { status: 400 });
    }
    if (!(file instanceof File)) {
      return new Response("Missing file field", { status: 400 });
    }

    return Response.json({
      title,
      fileName: file.name,
      mimeType: file.type,
      sizeBytes: file.size,
    });
  },
};
```

## Validating MIME type and file size before storing

```typescript
const ALLOWED_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
]);
const MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

function validateFile(
  file: File
): { ok: true } | { ok: false; error: string } {
  if (!ALLOWED_TYPES.has(file.type)) {
    return {
      ok: false,
      error: `Unsupported type ${file.type}. Allowed: ${[...ALLOWED_TYPES].join(", ")}`,
    };
  }
  if (file.size > MAX_SIZE_BYTES) {
    return {
      ok: false,
      error: `File too large (${file.size} bytes). Max: ${MAX_SIZE_BYTES}`,
    };
  }
  return { ok: true };
}
```

## Storing the uploaded file in R2

```typescript
import crypto from "node:crypto"; // available via workers-nodejs-compat

export async function storeUpload(
  env: Env,
  file: File,
  userId: string
): Promise<string> {
  const ext = file.name.split(".").pop()?.toLowerCase() ?? "bin";
  const key = `uploads/${userId}/${crypto.randomUUID()}.${ext}`;

  // file.stream() avoids a second copy vs file.arrayBuffer()
  await env.UPLOADS.put(key, file.stream(), {
    httpMetadata: {
      contentType: file.type,
      contentDisposition: `attachment; filename="${file.name}"`,
    },
    customMetadata: {
      originalName: file.name,
      uploadedBy: userId,
      uploadedAt: new Date().toISOString(),
    },
  });

  return key;
}
```

## Handling multiple file fields

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const form = await request.formData();

    // formData.getAll() returns all values for a repeated field name
    const files = form.getAll("files");
    const results: string[] = [];

    for (const entry of files) {
      if (!(entry instanceof File)) continue;

      const validation = validateFile(entry);
      if (!validation.ok) {
        return new Response(validation.error, { status: 400 });
      }

      const key = await storeUpload(env, entry, "anonymous");
      results.push(key);
    }

    return Response.json({ keys: results, count: results.length });
  },
};
```

## Full upload endpoint with D1 metadata persistence

```typescript
export interface Env {
  UPLOADS: R2Bucket;
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const form = await request.formData();
    const file = form.get("file");
    const userId = form.get("userId");

    if (!(file instanceof File) || typeof userId !== "string") {
      return new Response("Invalid form data", { status: 400 });
    }

    const validation = validateFile(file);
    if (!validation.ok) {
      return new Response(validation.error, { status: 422 });
    }

    // Store binary in R2
    const r2Key = await storeUpload(env, file, userId);

    // Store metadata in D1
    await env.DB.prepare(
      `INSERT INTO uploads (id, user_id, r2_key, file_name, mime_type, size_bytes, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
      .bind(
        crypto.randomUUID(),
        userId,
        r2Key,
        file.name,
        file.type,
        file.size,
        new Date().toISOString()
      )
      .run();

    return Response.json({ key: r2Key }, { status: 201 });
  },
};
```

## Anti-patterns

- **Trusting `file.type` as the authoritative MIME type.** The browser sets
  `Content-Type` of each part based on the file extension — a user can rename
  `malware.exe` to `photo.jpg`. For security-critical code, read the first few
  bytes (magic number) to verify the actual file type. Libraries like `file-type`
  can be bundled with the Worker.
- **Calling `file.arrayBuffer()` and then `file.stream()`.** `File` is a `Blob`;
  consuming it as a stream after reading the buffer (or vice versa) works, but
  it means two copies in memory. Pick one approach per upload — prefer
  `.stream()` for storage, `.arrayBuffer()` for inspection.
- **No file size limit before calling `request.formData()`.** A 500 MB upload
  will OOM the Worker before you can validate. Check `Content-Length` first, or
  enforce size at the CDN/WAF layer with a Cloudflare Request Size Limit rule.
- **Storing uploaded files directly under user-controlled keys.** Never use
  `file.name` as the R2 key. Generate a UUID key and store the original filename
  in metadata. Path traversal is not a risk in R2, but predictable keys allow
  key enumeration.
- **Accepting uploads without authentication.** Any public upload endpoint will
  be abused to store arbitrary content at your R2 cost. Gate uploads behind a
  Worker auth check or Cloudflare Access.

## Gotchas

- **`request.formData()` buffers the entire body.** Workers have a 128 MB
  memory limit (512 MB on Unbound). A 150 MB upload on a Standard Worker will
  throw `RangeError: Memory limit exceeded`. Use R2 presigned uploads for large
  files.
- **`file.type` is empty string when the browser cannot determine the MIME type.**
  This happens for uncommon extensions. Default to `application/octet-stream`
  and validate by magic bytes if type matters.
- **`formData()` on a non-multipart body throws** — it does not return an empty
  `FormData`. Always check `Content-Type` before calling it or wrap in try/catch.
- **`File.size` reports bytes, not characters.** For UTF-8 text files, the byte
  count may be higher than the visible character count. Report sizes in bytes
  to avoid confusion.
- **`wrangler dev` local mode uses a local disk R2 emulator** — large file
  writes succeed locally but may behave differently at the edge. Test against a
  real R2 bucket in staging before production deployment.

## Verification

```bash
# Test with curl multipart
curl -X POST https://worker.example.com/upload \
  -F "userId=u_123" \
  -F "file=@/path/to/photo.jpg;type=image/jpeg"
# → {"key":"uploads/u_123/<uuid>.jpg"}

# Confirm R2 object exists
npx wrangler r2 object get UPLOADS uploads/u_123/<uuid>.jpg --file /tmp/verify.jpg

# Test oversized file rejection (Content-Length check)
curl -X POST https://worker.example.com/upload \
  -F "file=@/path/to/large.bin" \
  -v
# → 422 or 413 depending on your WAF rule
```

## Related

- `cloudflare/r2-best-practices.md`
- `cloudflare/r2-presigned-url-cors-mobile-upload.md`
- `cloudflare/r2-multipart-upload.md`
- `cloudflare/d1-best-practices.md`
- Workers FormData API: https://developers.cloudflare.com/workers/runtime-apis/request/#the-body-of-a-request
- R2 Workers API: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/

## Sources

- https://developers.cloudflare.com/workers/examples/form-data/
- https://developer.mozilla.org/en-US/docs/Web/API/FormData
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
