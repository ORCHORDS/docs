# Workers R2 Gotchas

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You store audio files in R2 and serve them from a Worker. Users report that clicking a download link opens a raw binary stream in the browser instead of triggering a file download. Listing a directory-style prefix returns fewer objects than exist. A multipart upload silently fails with a part size error. After a bulk import, listing returns stale results for up to 15 seconds. These are all R2-specific behaviours that differ from S3 in subtle ways.

---

## Context

R2 is Cloudflare's S3-compatible object storage with zero egress fees. It is accessible from Workers via the native binding API (not the S3 SDK). The binding API differs from both the S3 REST API and the AWS SDK in key areas: metadata handling, listing semantics, and multipart upload constraints. R2 also has eventual consistency on list operations after puts, unlike S3's strong read-after-write consistency.

Orchords stores stems, mixed tracks, project exports, and user avatar images in R2. All six gotchas below have caused production bugs.

---

## Solution

```typescript
// workers-r2-gotchas.ts

interface Env {
  AUDIO_BUCKET: R2Bucket;
}

// ─────────────────────────────────────────────────────────────
// GOTCHA 1: put() without Content-Type causes download prompt
// ─────────────────────────────────────────────────────────────
//
// R2 stores whatever metadata you provide. If you omit
// httpMetadata.contentType, browsers receive application/octet-stream
// and show a "Save file" dialog instead of rendering inline.

const CONTENT_TYPES: Record<string, string> = {
  mp3: 'audio/mpeg',
  wav: 'audio/wav',
  flac: 'audio/flac',
  ogg: 'audio/ogg',
  m4a: 'audio/mp4',
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
  pdf: 'application/pdf',
};

function contentTypeFromKey(key: string): string {
  const ext = key.split('.').pop()?.toLowerCase() ?? '';
  return CONTENT_TYPES[ext] ?? 'application/octet-stream';
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1); // strip leading '/'

    if (request.method === 'PUT') {
      return handleUpload(request, env, key);
    }
    if (request.method === 'GET') {
      return handleDownload(request, env, key);
    }
    return new Response('Method not allowed', { status: 405 });
  },
};

async function handleUpload(
  request: Request,
  env: Env,
  key: string
): Promise<Response> {
  // WRONG — missing httpMetadata:
  // await env.AUDIO_BUCKET.put(key, request.body);

  // CORRECT — always set httpMetadata including contentType:
  await env.AUDIO_BUCKET.put(key, request.body, {
    httpMetadata: {
      contentType:
        request.headers.get('Content-Type') ?? contentTypeFromKey(key),
      contentDisposition: undefined, // let the browser decide
      cacheControl: 'public, max-age=31536000, immutable',
    },
    customMetadata: {
      uploadedBy: request.headers.get('X-User-Id') ?? 'unknown',
      uploadedAt: new Date().toISOString(),
    },
  });

  return new Response(JSON.stringify({ key }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function handleDownload(
  request: Request,
  env: Env,
  key: string
): Promise<Response> {
  const object = await env.AUDIO_BUCKET.get(key, {
    range: request.headers.has('Range')
      ? request.headers
      : undefined,
  });

  if (!object) {
    return new Response('Not found', { status: 404 });
  }

  const headers = new Headers();
  // Copy stored httpMetadata back to response headers
  object.writeHttpMetadata(headers);
  headers.set('ETag', object.httpEtag);

  // R2 does not set Content-Length automatically on ranged reads
  if (object.range) {
    const range = object.range as { offset: number; length: number };
    headers.set('Content-Range', `bytes ${range.offset}-${range.offset + range.length - 1}/${object.size}`);
    headers.set('Content-Length', String(range.length));
    return new Response(object.body, { status: 206, headers });
  }

  headers.set('Content-Length', String(object.size));
  return new Response(object.body, { status: 200, headers });
}

// ─────────────────────────────────────────────────────────────
// GOTCHA 2: R2 key length limit — 1024 bytes UTF-8
// ─────────────────────────────────────────────────────────────
//
// R2 keys are limited to 1024 bytes (not characters) of UTF-8.
// Constructing keys from user-supplied filenames without length
// checking causes a runtime error on upload.

function sanitiseKey(prefix: string, filename: string): string {
  // Normalise unicode, remove path traversal, truncate
  const safe = filename
    .normalize('NFC')
    .replace(/\.\.[\/\\]/g, '') // strip path traversal
    .replace(/[^a-zA-Z0-9._\-\/]/g, '_'); // allow safe chars only

  const key = `${prefix}/${safe}`;
  const encoded = new TextEncoder().encode(key);

  if (encoded.length <= 1024) return key;

  // Truncate to 1024 bytes, preserving extension
  const ext = safe.split('.').pop() ?? '';
  const extBytes = new TextEncoder().encode(`.${ext}`);
  const maxBase = 1024 - extBytes.length;

  // Slice at byte boundary
  const truncated = new TextDecoder().decode(encoded.slice(0, maxBase));
  return `${truncated}.${ext}`;
}

// ─────────────────────────────────────────────────────────────
// GOTCHA 3: Listing with delimiter returns truncated results
//           without cursor — you must paginate
// ─────────────────────────────────────────────────────────────
//
// bucket.list({ prefix, delimiter }) with no cursor only returns
// up to 1000 objects per call. If a prefix contains more than
// 1000 objects, you silently lose the rest.

async function listAll(
  bucket: R2Bucket,
  prefix: string,
  delimiter?: string
): Promise<R2Object[]> {
  const objects: R2Object[] = [];
  let cursor: string | undefined;

  do {
    const result = await bucket.list({
      prefix,
      delimiter,
      limit: 1000,
      cursor,
    });

    objects.push(...result.objects);

    // When truncated is true, result.cursor contains the continuation token
    cursor = result.truncated ? result.cursor : undefined;
  } while (cursor !== undefined);

  return objects;
}

// ─────────────────────────────────────────────────────────────
// GOTCHA 4: Multipart upload part size minimum is 5 MB
// ─────────────────────────────────────────────────────────────
//
// R2 requires all parts except the last to be at least 5 MB.
// Parts smaller than 5 MB cause the complete() call to throw.
// Unlike S3, R2 enforces this at complete() time, not at
// uploadPart() time, so you only discover the error at the end.

const MIN_PART_SIZE = 5 * 1024 * 1024; // 5 MB
const MAX_PARTS = 10_000;

async function multipartUpload(
  bucket: R2Bucket,
  key: string,
  data: ReadableStream<Uint8Array>,
  totalSize: number
): Promise<void> {
  const upload = await bucket.createMultipartUpload(key, {
    httpMetadata: { contentType: contentTypeFromKey(key) },
  });

  const parts: R2UploadedPart[] = [];
  const reader = data.getReader();
  let partNumber = 1;
  let buffer = new Uint8Array(0);
  let bytesRemaining = totalSize;

  try {
    while (true) {
      const { value, done } = await reader.read();

      if (value) {
        // Append chunk to buffer
        const merged = new Uint8Array(buffer.length + value.length);
        merged.set(buffer);
        merged.set(value, buffer.length);
        buffer = merged;
        bytesRemaining -= value.length;
      }

      // Upload a part when buffer >= 5 MB, OR on the last chunk
      const isLast = done || bytesRemaining === 0;
      if (buffer.length >= MIN_PART_SIZE || (isLast && buffer.length > 0)) {
        const part = await upload.uploadPart(partNumber, buffer);
        parts.push(part);
        partNumber++;
        buffer = new Uint8Array(0);
      }

      if (done || partNumber > MAX_PARTS) break;
    }

    await upload.complete(parts);
  } catch (err) {
    // Always abort on error to avoid orphaned multipart uploads
    // that are billed for storage until they expire (7 days default)
    await upload.abort();
    throw err;
  }
}

// ─────────────────────────────────────────────────────────────
// GOTCHA 5: R2 eventual consistency on list after put
// ─────────────────────────────────────────────────────────────
//
// After a put(), subsequent list() calls may not immediately
// return the new object. The window is typically <1 s but can
// reach 15 s under high write load. Do not rely on list()
// immediately after put() in the same request path.
//
// Pattern: track newly uploaded keys in KV with a short TTL,
// and merge the KV set into list() results on reads.

interface Env2 extends Env {
  RECENT_UPLOADS: KVNamespace;
}

async function listWithRecentUploads(
  env: Env2,
  prefix: string
): Promise<string[]> {
  // Fetch listed objects and recent KV uploads in parallel
  const [listed, recent] = await Promise.all([
    listAll(env.AUDIO_BUCKET, prefix),
    env.RECENT_UPLOADS.list({ prefix }),
  ]);

  const keys = new Set(listed.map((o) => o.key));
  for (const kv of recent.keys) {
    keys.add(kv.name.replace('recent:', ''));
  }

  return Array.from(keys).sort();
}

async function putWithRecentTracking(
  env: Env2,
  key: string,
  body: ReadableStream,
  contentType: string
): Promise<void> {
  await Promise.all([
    env.AUDIO_BUCKET.put(key, body, {
      httpMetadata: { contentType },
    }),
    env.RECENT_UPLOADS.put(`recent:${key}`, '1', { expirationTtl: 30 }),
  ]);
}
```

---

## Implementation Details

**`writeHttpMetadata(headers)`** is the canonical way to copy R2-stored metadata back onto a response. It populates `Content-Type`, `Cache-Control`, `Content-Encoding`, and `Content-Disposition` from the values stored at `put()` time. Manually re-setting these from `object.httpMetadata` is error-prone because the field names differ slightly from HTTP header names.

**Key naming conventions** — R2 uses flat key namespaces, not true directories. A `delimiter` of `/` in `list()` simulates directory listings by grouping keys that share a prefix up to the delimiter into `delimitedPrefixes`. Objects at that "level" are in `result.objects`; subdirectory prefixes are in `result.delimitedPrefixes`.

**Multipart upload lifecycle** — R2 stores incomplete multipart uploads and bills for their storage. An aborted upload is billed until the abort call succeeds. Always wrap multipart logic in `try/catch` and call `abort()` on failure. Use the R2 lifecycle rules (in the dashboard or via API) to auto-abort uploads older than 7 days.

**Range requests** — R2 supports byte range reads via the `range` option on `get()`. Pass `request.headers` as the range value and R2 will parse `Range: bytes=start-end` automatically. Check `object.range` on the response to build the `Content-Range` response header.

---

## Anti-patterns

- Calling `bucket.put(key, body)` without `httpMetadata.contentType` for user-facing files.
- Building R2 keys from raw user-supplied filenames without sanitising or length-checking.
- Calling `bucket.list({ prefix })` once and assuming you have all objects when a prefix may contain >1000 keys.
- Uploading a multipart object with parts smaller than 5 MB (except the last part) — complete() will throw.
- Treating R2 `list()` as strongly consistent immediately after `put()` in high-write scenarios.
- Never calling `upload.abort()` on multipart upload failure — results in orphaned uploads billed for 7 days.

---

## Gotchas

- `R2Object.body` is a `ReadableStream` — it can only be consumed once. If you need to inspect the body and also stream it to the response, use `object.arrayBuffer()` or `object.text()` and re-wrap.
- `bucket.head(key)` returns metadata without the body and is cheaper than `get()` for existence checks.
- Custom metadata values in `customMetadata` are stored as strings. Numbers, booleans, and objects must be serialised to strings at write time and parsed at read time.
- R2 object size limit is 5 TB per object via multipart upload; single-part uploads are limited to 5 GB.
- The `R2Bucket.list()` `cursor` field is only present on the response when `truncated` is `true`. Reading it when `truncated` is `false` returns `undefined`, not an empty string.
- Conditional writes (`onlyIf`) use ETags that are MD5 checksums. Unlike S3, R2 ETags for multipart uploads are not the composite MD5; do not compare them with S3-generated ETags.

---

## Verification

```typescript
// Test that contentType is correctly stored and returned
const mf = new Miniflare({ r2Buckets: ['AUDIO_BUCKET'] });
const bucket = await mf.getR2Bucket('AUDIO_BUCKET');

await bucket.put('test.mp3', new Uint8Array([0xFF, 0xFB]), {
  httpMetadata: { contentType: 'audio/mpeg' },
});

const obj = await bucket.get('test.mp3');
const headers = new Headers();
obj!.writeHttpMetadata(headers);

console.assert(
  headers.get('Content-Type') === 'audio/mpeg',
  'Content-Type must survive put/get round-trip'
);

// Test pagination completeness
const keys = Array.from({ length: 1500 }, (_, i) => `song:${i.toString().padStart(6, '0')}`);
await Promise.all(keys.map((k) => bucket.put(k, 'x')));
const all = await listAll(bucket, 'song:');
console.assert(all.length === 1500, `Expected 1500 objects, got ${all.length}`);
```

---

## Related

- `documentation/categories/lessons/workers-durable-object-pitfalls.md`
- `documentation/categories/lessons/workers-wrangler-deploy-surprises.md`
- Cloudflare R2 documentation: Objects, Multipart Uploads, Listing objects

---

## Sources

- Cloudflare R2 Workers API docs (2025)
- Orchords production incident log #R2-003 (missing Content-Type), #R2-009 (list pagination), #R2-017 (multipart part size)
- Cloudflare status page incident 2024-11: R2 list consistency window
