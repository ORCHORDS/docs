# Cloudflare R2: Object Lifecycle and Multipart Upload

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A user uploading a profile video (200 MB+) gets a connection
drop at 60 % and must restart from scratch. Browser-direct
uploads from mobile fail with CORS errors. Incomplete
uploads accumulate in the bucket with no automatic cleanup.
Content-Type headers are missing on served objects, forcing
clients to guess the media type.

## Context

WAM (example.com) stores user profile videos, avatar images,
and verification selfies in R2. Files range from a few KB
to several GB. The upload path is: mobile client → Worker
(generates presigned URL) → client uploads directly to R2.
This entry covers the complete multipart upload lifecycle,
presigned URL generation, CORS setup for cross-origin
browser uploads, and the aws4fetch / S3 SDK compatibility
layer.

## 1. Multipart Upload API (Workers Binding)

R2 exposes multipart upload through four binding methods.
The state (uploadId, part ETags) lives on the client; the
Worker is stateless.

```typescript
// ── Step 1: Create ─────────────────────────────────────
const upload = await env.MEDIA_BUCKET.createMultipartUpload(
  `uploads/${userId}/${fileName}`,
  {
    httpMetadata: {
      contentType:  "video/mp4",
      cacheControl: "private, max-age=0",
    },
    customMetadata: {
      userId:    userId,
      uploadedAt: new Date().toISOString(),
    },
  },
);
// Return { key, uploadId } to the client.

// ── Step 2: Upload Parts ────────────────────────────────
// Called once per part from the client-side orchestrator.
const part = await upload.uploadPart(
  partNumber,  // 1-based integer
  partBody,    // ReadableStream | ArrayBuffer | string
);
// Return part.etag to the client for completion.

// ── Step 3: Complete ────────────────────────────────────
const object = await upload.completeMultipartUpload(
  uploadedParts, // Array<{ partNumber: number; etag: string }>
);

// ── Step 4: Abort (on error) ───────────────────────────
await upload.abort();
```

Parts must be uploaded **in any order** but the `parts`
array passed to `completeMultipartUpload` must be sorted
in ascending `partNumber` order.

## 2. Part Size Constraints and Limits

| Constraint              | Value                          |
|-------------------------|--------------------------------|
| Minimum part size       | 5 MiB (all parts except last)  |
| Last part minimum       | 1 byte                         |
| Maximum part size       | 5 GiB                          |
| Maximum part count      | 10,000 parts                   |
| Maximum object size     | 5 TiB                          |
| uploadId expiry         | 7 days (after last activity)   |

The 5 MiB floor means a 50 MiB file must be split into at
least 10 parts. A common split strategy: `chunkSize = 10 MiB`
for files above 100 MiB; single-part PUT for smaller files.

**Incomplete upload cleanup:** R2 does not yet support S3-
style lifecycle rules to auto-abort incomplete multipart
uploads. Implement a cron Worker that calls
`bucket.list({ prefix: "uploads/incomplete/" })` and
aborts uploads older than 24 hours using a stored record
of `uploadId` values in D1.

## 3. Presigned URLs for Browser-Direct Upload

The Worker generates time-limited presigned URLs that let
the browser upload directly to R2 without proxying through
the Worker. Uses the AWS SDK v3 S3 client pointed at the
R2 S3-compatible endpoint.

```typescript
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl }               from "@aws-sdk/s3-request-presigner";

const r2 = new S3Client({
  region:   "auto",
  endpoint: `https://${env.CF_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId:     env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  },
});

export async function generatePresignedPut(
  key:         string,
  contentType: string,
  expiresIn:   number = 3600,
): Promise<string> {
  const cmd = new PutObjectCommand({
    Bucket:      "wam-media",
    Key:         key,
    ContentType: contentType,
  });
  return getSignedUrl(r2, cmd, { expiresIn });
}
```

Supported operations for presigned URLs: `GET`, `PUT`,
`HEAD`, `DELETE`. `POST` (HTML multipart form) is not
supported. Presigned URLs work only with the S3 API
hostname (`<ACCOUNT_ID>.r2.cloudflarestorage.com`), not
custom public domains.

Expiry range: 1 second to 7 days. For browser uploads,
use 15–60 minutes. Treat the URL as a bearer token —
anyone possessing it can upload until expiry.

## 4. CORS Configuration for Cross-Origin Browser Uploads

Without CORS rules the browser blocks the presigned PUT
from example project origin (`example.com`) to the R2 endpoint.
Configure CORS via the R2 dashboard or the S3 API:

```json
[
  {
    "AllowedOrigins": [
      "https://example.com",
      "https://staging.example.com"
    ],
    "AllowedMethods": ["PUT", "GET", "HEAD"],
    "AllowedHeaders": [
      "Content-Type",
      "Content-Length",
      "Cache-Control",
      "x-amz-meta-*"
    ],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

`ExposeHeaders: ["ETag"]` is required so the browser can
read the part ETag from the PUT response headers and pass
it back to the Worker for `completeMultipartUpload`.

The `Content-Type` header in the presigned URL signature
must exactly match what the browser sends. Mismatches
cause `SignatureDoesNotMatch` (403). Always specify
`ContentType` in `PutObjectCommand` and instruct the
client to pass the same value in the `Content-Type`
header of the PUT request.

## 5. R2 vs S3 SDK Compatibility (aws4fetch)

For Worker environments where the full AWS SDK is too
heavy, use `aws4fetch` — a lightweight AWS Signature v4
implementation that works in the Workers runtime.

```typescript
import { AwsClient } from "aws4fetch";

const r2 = new AwsClient({
  accessKeyId:     env.R2_ACCESS_KEY_ID,
  secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  region:          "auto",
  service:         "s3",
});

// Single-part upload (< 5 MiB)
const resp = await r2.fetch(
  `https://${env.CF_ACCOUNT_ID}.r2.cloudflarestorage.com/\
wam-media/${key}`,
  {
    method:  "PUT",
    headers: { "Content-Type": contentType },
    body:    fileBuffer,
  },
);
```

| Feature                  | AWS SDK v3         | aws4fetch           |
|--------------------------|--------------------|---------------------|
| Bundle size (minified)   | ~300 KB+           | ~5 KB               |
| Presigned URL helper     | `getSignedUrl()`   | Manual signing      |
| Multipart upload helper  | `Upload` class     | Manual (raw API)    |
| Workers compatibility    | Requires Node compat| Native              |
| TypeScript types         | Full               | Minimal             |

For production multipart flows use the **Workers R2 binding
API** (§1) rather than either SDK — it is zero-latency
(no HTTP overhead) and has no bundle cost.

## Anti-patterns

- Uploading files through the Worker body rather than via
  presigned URL — Worker request body is limited to the
  Workers platform's request size limit and proxying wastes
  CPU and egress.
- Calling `completeMultipartUpload` with parts in random
  order — parts must be ascending by `partNumber`.
- Assuming incomplete uploads disappear automatically — R2
  has no lifecycle rules as of 2026; stale incomplete
  uploads must be cleaned up by a cron job.
- Setting a `Cache-Control: public` header on user-private
  content served via a public R2 custom domain.

## Gotchas

- Every part except the last must be ≥ 5 MiB. A part
  smaller than 5 MiB that is not the final part causes
  `EntityTooSmall` on complete.
- `uploadId` values expire after 7 days of inactivity.
  Store them durably (D1) when resumable uploads must
  survive page refreshes.
- `POST` multipart form uploads (HTML `<input type="file">`)
  are not supported via presigned URLs — use `PUT` with a
  presigned URL and `XMLHttpRequest` or `fetch`.
- Presigned URLs are tied to the S3 API hostname, not the
  R2 public custom domain (`pub-<hash>.r2.dev` or a custom
  domain). Browsers uploading to the S3 hostname need CORS
  rules on the bucket.
- `ETag` values on multipart-completed objects are not MD5
  checksums — they are a composite of part ETags. Do not
  use them for content integrity verification.

## Verification

1. Upload a 15 MiB test file in three 5 MiB parts via the
   Workers binding and confirm `completeMultipartUpload`
   returns an R2Object with a non-null `key`.
2. Generate a presigned PUT URL; `curl -T testfile.mp4`
   to it and confirm `200 OK` with an `ETag` header.
3. From a browser on `example.com`, perform a `fetch` PUT
   to the presigned URL and confirm no CORS errors in
   DevTools Network.
4. Check the uploaded object's `Content-Type` in the
   R2 dashboard to confirm metadata is stored correctly.
5. Test abort: start an upload, call `abort()`, and verify
   the key does not appear in `bucket.list()`.

## Related

- `r2-best-practices.md` — general R2 usage patterns
- `r2-presigned-url-cors-mobile-upload.md`
- `r2-cors-config.md` — bucket-level CORS setup guide
- `r2-large-file-patterns.md` — HLS segmentation pipeline
- `r2-lifecycle-rules.md` — current R2 lifecycle rule state
- `workers-cron-triggers.md` — scheduling incomplete-upload
  cleanup jobs

## Source URLs (verified 2026-08-17)

- https://developers.cloudflare.com/r2/api/workers/workers-multipart-usage/
- https://developers.cloudflare.com/r2/objects/upload-objects/
- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://developers.cloudflare.com/r2/platform/limits/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
