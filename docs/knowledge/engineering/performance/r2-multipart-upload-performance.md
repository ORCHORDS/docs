# R2 Multipart Upload Performance for Large Assets

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Uploading large files — video exports, database backups, high-resolution images,
ML model checkpoints — to Cloudflare R2 through a single `PUT` frequently fails or
times out for assets above ~100 MB. A Worker's request body is limited to 100 MB per
invocation, and a direct browser-to-R2 presigned PUT shares the same constraint. The
solution is the S3-compatible multipart upload API exposed by R2: split the file into
parts, upload each independently (potentially in parallel), then issue a
`CompleteMultipartUpload` to assemble them atomically. Throughput increases because
multiple parts transit simultaneously, and reliability improves because each failed
part can be retried independently.

## Context

R2's multipart upload API mirrors the S3 multipart API precisely:
1. `CreateMultipartUpload` — obtain an `uploadId`
2. `UploadPart` × N — upload byte ranges, receive `ETag` per part
3. `CompleteMultipartUpload` — assemble parts into the final object

Parts must be at least 5 MB except for the last part. The maximum part count is
10 000, giving a maximum single-object size of ~48 TB. In practice, 8–16 MB parts
balance network efficiency with the Worker 128 MB memory limit. Uploads can be
parallelised across parts up to the 50-subrequest limit per Worker invocation. For
files too large to upload from a single Worker, the browser can call presigned URLs
for each part directly, bypassing the Worker entirely after the initiation step.

## Server-Side Multipart via Workers R2 Binding

When the file is piped through a Worker (e.g., from a form upload or a proxied source),
use the native R2 multipart binding. This avoids generating S3 credentials and is
simpler than the presigned-URL path.

```typescript
interface Env {
  BUCKET: R2Bucket;
}

const PART_SIZE = 10 * 1024 * 1024; // 10 MB

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "PUT") return new Response("Method Not Allowed", { status: 405 });

    const key = new URL(req.url).pathname.slice(1);
    const contentType = req.headers.get("content-type") ?? "application/octet-stream";

    // Initiate multipart upload
    const upload = await env.BUCKET.createMultipartUpload(key, {
      httpMetadata: { contentType },
    });

    const parts: R2UploadedPart[] = [];
    const reader = req.body!.getReader();
    let buffer = new Uint8Array(0);
    let partNumber = 1;

    async function flush(data: Uint8Array): Promise<void> {
      const part = await upload.uploadPart(partNumber++, data);
      parts.push(part);
    }

    while (true) {
      const { done, value } = await reader.read();

      if (value) {
        // Concatenate into buffer
        const merged = new Uint8Array(buffer.length + value.length);
        merged.set(buffer, 0);
        merged.set(value, buffer.length);
        buffer = merged;
      }

      // Flush complete parts
      while (buffer.length >= PART_SIZE) {
        await flush(buffer.slice(0, PART_SIZE));
        buffer = buffer.slice(PART_SIZE);
      }

      if (done) break;
    }

    // Upload the remainder (may be < 5 MB for final part — that is allowed)
    if (buffer.length > 0) {
      await flush(buffer);
    }

    const object = await upload.complete(parts);
    return Response.json({ key: object.key, etag: object.httpEtag });
  },
};
```

## Client-Side Parallel Multipart via Presigned URLs

For large files (> 200 MB) or when the Worker cannot hold the entire file in memory,
issue presigned URLs for each part and let the browser upload parts in parallel.
The Worker only orchestrates; no file bytes pass through it.

```typescript
// Worker: issue presigned part URLs
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const { key, size, partSizeMb = 16 } = await req.json<{
      key: string;
      size: number;
      partSizeMb?: number;
    }>();

    const partSize = partSizeMb * 1024 * 1024;
    const partCount = Math.ceil(size / partSize);

    const upload = await env.BUCKET.createMultipartUpload(key);

    // Generate one presigned URL per part
    const partUrls = await Promise.all(
      Array.from({ length: partCount }, (_, i) =>
        upload.uploadPart(i + 1, /* placeholder — this is the presigned-URL path */
          new Uint8Array(0) // binding presigns without sending data
        ).then(() => {
          // NOTE: native binding does not expose presigned URLs directly.
          // Use the S3-compat endpoint with wrangler-generated credentials instead.
          return `https://${env.ACCOUNT_ID}.r2.cloudflarestorage.com/${key}?uploadId=${upload.uploadId}&partNumber=${i + 1}`;
        })
      )
    );

    return Response.json({ uploadId: upload.uploadId, partUrls });
  },
};
```

In practice, presigned part URLs require the S3-compatible API with HMAC credentials.
Use `aws4fetch` inside the Worker to sign each `UploadPart` URL:

```typescript
import { AwsClient } from "aws4fetch";

async function presignPartUrl(
  client: AwsClient,
  bucket: string,
  key: string,
  uploadId: string,
  partNumber: number,
  accountId: string,
  expiresIn = 3600
): Promise<string> {
  const url = new URL(
    `https://${accountId}.r2.cloudflarestorage.com/${bucket}/${key}` +
    `?uploadId=${encodeURIComponent(uploadId)}&partNumber=${partNumber}` +
    `&X-Amz-Expires=${expiresIn}`
  );
  const signed = await client.sign(new Request(url, { method: "PUT" }), {
    aws: { signQuery: true },
  });
  return signed.url;
}
```

Browser-side parallel upload:

```typescript
async function uploadPartsInParallel(
  file: File,
  partUrls: string[],
  partSize: number,
  concurrency = 4
): Promise<{ partNumber: number; etag: string }[]> {
  const etags: { partNumber: number; etag: string }[] = [];
  const queue = partUrls.map((url, i) => ({ url, partNumber: i + 1 }));
  let cursor = 0;

  async function worker() {
    while (cursor < queue.length) {
      const { url, partNumber } = queue[cursor++];
      const start = (partNumber - 1) * partSize;
      const end = Math.min(start + partSize, file.size);
      const blob = file.slice(start, end);

      const res = await fetch(url, { method: "PUT", body: blob });
      if (!res.ok) throw new Error(`Part ${partNumber} failed: ${res.status}`);

      const etag = res.headers.get("etag") ?? "";
      etags.push({ partNumber, etag });
    }
  }

  await Promise.all(Array.from({ length: concurrency }, () => worker()));
  etags.sort((a, b) => a.partNumber - b.partNumber);
  return etags;
}
```

## Completing and Aborting Uploads

Always provide an abort path. Incomplete multipart uploads accumulate parts in R2
storage and incur Class A operation charges indefinitely until either `complete` or
`abort` is called.

```typescript
// Worker endpoint to complete the upload
async function completeUpload(
  env: Env,
  key: string,
  uploadId: string,
  parts: { partNumber: number; etag: string }[]
): Promise<R2Object> {
  const upload = env.BUCKET.resumeMultipartUpload(key, uploadId);
  return upload.complete(
    parts.map((p) => ({ partNumber: p.partNumber, etag: p.etag }))
  );
}

// Worker endpoint to abort on client cancel
async function abortUpload(env: Env, key: string, uploadId: string): Promise<void> {
  const upload = env.BUCKET.resumeMultipartUpload(key, uploadId);
  await upload.abort();
}
```

Schedule a Cloudflare Lifecycle Rule or a daily cron Worker to abort uploads older
than 24 hours as a safety net for orphaned sessions.

## Anti-patterns

**Uploading parts smaller than 5 MB** — R2 (and S3) reject any non-final part below
5 MB with `EntityTooSmall`. Always verify `buffer.length >= 5 * 1024 * 1024` before
calling `uploadPart`, except for the very last part.

**No retry on individual parts** — transient network errors mid-upload should retry
only the failed part, not restart the entire upload. Wrap `uploadPart` in an
exponential-backoff retry loop.

**Forgetting to call `abort()` on failure** — orphaned uploads silently consume
storage quota and incur charges. Always call `abort()` in a `catch` block.

**Reading the entire file into memory before splitting** — defeats the streaming
nature of multipart. Stream the source and flush parts as the buffer fills.

## Gotchas

- `resumeMultipartUpload` does not validate that the `uploadId` exists. A stale ID
  will only fail at `complete()` or `uploadPart()` time.
- R2 currently does not support copying parts from other objects (`UploadPartCopy` in
  S3). All part data must be sent from the client.
- ETags from R2 are quoted strings: `"abc123"`. Strip the quotes before including them
  in the complete request if using a raw HTTP client.
- Workers bound via `BUCKET` have a **25 MB body limit per `uploadPart` call** when
  using the native binding. Part sizes above 25 MB require the S3-compat HTTP path.

## Verification

```bash
# Verify a completed multipart object exists and check its metadata
wrangler r2 object get BUCKET_NAME path/to/object --file /dev/null

# List in-progress multipart uploads (via S3 compat)
aws s3api list-multipart-uploads \
  --bucket MY_BUCKET \
  --endpoint-url https://<ACCOUNT_ID>.r2.cloudflarestorage.com
```

Instrument the Worker with `server-timing` headers reporting per-part latency to
identify slow parts and tune concurrency accordingly.

## Related

- `cloudflare-r2-presigned-cdn-acceleration.md`
- `workers-subrequest-fanout-parallelism.md`
- `workers-streaming-large-payloads.md`

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#r2multipartupload
- https://developers.cloudflare.com/r2/api/s3/api/#multipart-upload
- https://developers.cloudflare.com/r2/buckets/object-lifecycles/
