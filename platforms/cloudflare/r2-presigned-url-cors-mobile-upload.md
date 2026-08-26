# R2 Presigned URL Uploads from Mobile Browsers

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Uploads succeed on desktop Chrome/Firefox but fail on iOS
Safari or inside an Android WebView:

- CORS preflight rejected: `No 'Access-Control-Allow-Origin'
  header is present on the requested resource`
- `403 Forbidden` body `SignatureDoesNotMatch` — browser
  sends a `Content-Type` that differs from the signed value
- Silent PUT timeout on iOS 18 over cellular: preflight
  returns 200 but the `PUT` is never dispatched
- Android WebView `SignatureDoesNotMatch` while the same
  URL works in desktop Chrome

## Context

example project uses R2 for user content (photos, attachments,
exports). Upload path: browser → Worker issues presigned
PUT → browser PUTs directly to R2. Desktop masks CORS and
Content-Type issues that surface only on mobile.

## R2 CORS Configuration

```bash
wrangler r2 bucket cors set <bucket> --file cors.json
```

```json
[
  {
    "AllowedOrigins": ["https://app.example.com"],
    "AllowedMethods": ["GET","PUT","HEAD","POST","DELETE"],
    "AllowedHeaders": [
      "content-type","content-md5","x-amz-date",
      "x-amz-content-sha256","x-amz-security-token"
    ],
    "ExposeHeaders": ["ETag","Content-Length"],
    "MaxAgeSeconds": 3600
  }
]
```

- List `content-type` explicitly. Wildcard `"*"` in
  `AllowedHeaders` is silently ignored by R2; preflights
  that request `content-type` are rejected.
- Never pair `AllowedOrigins: ["*"]` with `AllowedHeaders`
  containing `Authorization` — browsers reject that combo.
- `ETag` must be in `ExposeHeaders` or `fetch()` cannot
  read it — required for multipart-complete flows.
- Bucket CORS applies only to the **public URL** (custom
  domain or `pub-*.r2.dev`). Requests through a Worker
  binding bypass bucket CORS; the Worker must add
  `Access-Control-*` headers itself.

## Signing: Worker Binding vs S3-Compat API

**Worker binding (recommended)** — no R2 keys in code:

```typescript
// Pages Function / Worker
const url = await env.BUCKET.createPresignedUrl({
  method: 'PUT',
  key,                         // `users/${uid}/photo.jpg`
  expiresIn: 600,
  httpMetadata: { contentType }, // R2 enforces on upload
});
return Response.json({ url });
```

**S3-compat API (aws4fetch)** works for server-side scripts
holding long-lived R2 API keys. Do not include `Content-Type`
when using `signQuery: true` — the value is baked into the
HMAC and any browser mismatch returns 403. Prefer the Worker
binding; it avoids key management and this trap entirely.

## Multipart Upload with Per-Part Retry

Single-part PUTs fail unrecoverably on mobile network
drops. Multipart isolates failures to individual chunks.

```typescript
// Worker: initiate + sign each part
const mp = await env.BUCKET.createMultipartUpload(
  key, { httpMetadata: { contentType } }
);
const partUrl = await env.BUCKET.createPresignedUrl({
  method: 'PUT', key, expiresIn: 3600,
  multipartUploadId: mp.uploadId, partNumber,
});

// Browser: retry with exponential backoff
async function uploadPart(
  url: string, blob: Blob, attempt = 0,
): Promise<string> {
  const res = await fetch(url, { method: 'PUT', body: blob });
  if (!res.ok) {
    if (attempt >= 3) throw new Error(`HTTP ${res.status}`);
    await new Promise(r => setTimeout(r, 2**attempt * 1000));
    return uploadPart(url, blob, attempt + 1);
  }
  return res.headers.get('ETag')!;
}
```

Mobile chunking rules:

- Minimum part size is 5 MB (R2/S3 floor); target **8 MB**
  on Wi-Fi, **4–5 MB** when
  `navigator.connection.effectiveType` is `'4g'` or lower.
- Upload parts **sequentially** — parallel parts saturate
  the mobile radio and raise the failure rate.
- Persist `{ uploadId, completedParts }` in `sessionStorage`
  for resume after page reload; add an R2 lifecycle rule to
  abort stale uploads after 24 h.

**Progress events:** `fetch()` has no upload-progress API
on mobile. Use `XMLHttpRequest`: `xhr.upload.onprogress =
e => onProgress(e.loaded / e.total)` when `e.lengthComputable`.

## Content-Type, iOS, and Android Quirks

**Content-Type mismatch** is the most common mobile 403:
read `file.type` before requesting a URL, pass it to the
Worker, set `httpMetadata: { contentType }`, and always
set `Content-Type` explicitly on the PUT.

*iOS Camera:* `file.type` may report `image/jpeg` for files
that are `image/heic` on iOS 16+. Accept both and normalize
server-side before signing.

*iOS 18 cellular:* PUT hangs after a successful preflight
when the file exceeds ~1 MB over mobile data (no platform
fix as of 2026-08-17). Reduce the first chunk to 3–4 MB
on cellular and add a 15 s `AbortSignal` timeout.

*iOS blob URLs:* `URL.createObjectURL(file)` is bound to
the current origin. Cross-origin R2 PUT with a `blob:` URL
fails at the browser layer; R2 never receives the request.
Pass the raw `File` or `Blob` directly to `fetch()` / XHR.

*Android WebView:* Apps serving the upload UI from
`file://` fail all CORS preflights. Serve the UI on a real
`https://` origin matching an `AllowedOrigins` entry.

## CDN Caching and Presigned GET URLs

Presigned GET URLs are **never cached** by Cloudflare CDN.
Each URL is unique (HMAC + expiry in query params);
Cloudflare returns `cf-cache-status: BYPASS` every time.
Every hit is a billable Class B R2 read.

For public assets: attach a **custom domain** to the bucket
(R2 dashboard → Settings → Custom Domains); Cloudflare
caches eligible MIME types by default, add a Cache Rule for
others. Never put private objects behind a custom domain —
it exposes the entire bucket. For private assets, use
short-lived presigned GETs (≤ 5 min) and accept the
per-miss Class B cost.

## Anti-patterns

- **`AllowedHeaders: ["*"]`** — R2 ignores wildcards; list
  headers explicitly.
- **Signing Content-Type with `signQuery: true`** — bakes
  the value into the HMAC; any header mismatch = 403.
- **Single-part PUT over 5 MB on mobile** — one drop
  restarts the full upload; use multipart with sequential
  parts (parallel saturates the mobile radio).
- **`blob:` URL as the PUT body** — iOS blocks cross-origin
  blob reads; pass `File` / `Blob` directly.
- **Presigned GET URLs for CDN delivery** — each URL is
  unique and permanently uncacheable.

## Gotchas

- CORS changes take up to 30 s to reach all edge nodes.
  `MaxAgeSeconds: 3600` also caches preflights in browsers
  for an hour — plan config deployments accordingly.
- `uploadId` is distinct from the object key; persist both
  for reliable resume after a page reload.
- iOS 18 cellular timeout is unpatched as of 2026-08-17;
  smaller chunks and retries are the only mitigation.

## Verification

```bash
# Check applied CORS policy:
wrangler r2 bucket cors get <bucket-name>

# Simulate a browser preflight:
curl -v -X OPTIONS \
  "https://<custom-domain>/uploads/test.jpg" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type"
# Expect: 200, Access-Control-Allow-Origin present
```

Manual: upload a 12 MB file from iOS over cellular and
confirm chunks retry on simulated packet loss. Verify a
presigned GET URL returns `cf-cache-status: BYPASS` and a
custom-domain public asset returns `HIT` on second fetch.

## Related

- `cloudflare/r2-cors-config.md`
- `cloudflare/r2-signed-urls.md`
- `cloudflare/r2-multipart-upload.md`
- `cloudflare/r2-custom-domains-cache-rules.md`
- `cloudflare/r2-large-file-patterns.md`

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://developers.cloudflare.com/r2/buckets/cors/
- https://developers.cloudflare.com/cache/interaction-cloudflare-products/r2/
- https://developer.apple.com/forums/thread/764420
- https://community.cloudflare.com/t/does-pre-signed-url-support-cache-when-get-an-object-from-r2/777061
- https://dev.to/ehteshamdev/how-to-fix-cors-error-while-uploading-files-on-cloudflare-r2-using-presigned-urls-21dm
