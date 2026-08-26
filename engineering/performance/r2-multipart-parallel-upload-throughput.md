# R2 Multipart Parallel Upload Throughput

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Uploading large files (>100 MB) to R2 from a Worker or an edge script is slow because the entire object is transferred as a single `put()` call, which serialises the upload and provides no retry granularity on failure. Switching to multipart uploads with parallel part transfers reduces wall-clock upload time by up to 4–8× for large objects and makes partial retries possible without restarting the entire transfer.

## Context

R2 implements the S3-compatible multipart upload API: `createMultipartUpload`, `uploadPart`, and `completeMultipartUpload`. Each part must be at least 5 MB (except the final part), and the maximum number of parts is 10,000. The key performance lever is uploading multiple parts concurrently — each part becomes an independent R2 subrequest, and the Workers runtime can run up to 1,000 concurrent subrequests per invocation. In practice, 4–8 concurrent part uploads fully saturate available bandwidth while staying well within CPU time limits.

For uploads originating from the client browser, the Worker acts as a coordinator: it creates the multipart upload, returns pre-signed part URLs, and assembles the final object when the client reports all parts complete.

## 1. Direct Parallel Upload from a Worker

```typescript
// lib/r2-multipart.ts

const PART_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB per part
const MAX_CONCURRENCY  = 6;                // parallel part uploads

export interface UploadResult {
  key:  string;
  etag: string;
}

/**
 * Uploads an ArrayBuffer to R2 using parallel multipart upload.
 * Falls back to a single put() for objects smaller than 2× PART_SIZE.
 */
export async function parallelUpload(
  bucket: R2Bucket,
  key: string,
  body: ArrayBuffer,
  contentType: string
): Promise<UploadResult> {
  if (body.byteLength < PART_SIZE_BYTES * 2) {
    const obj = await bucket.put(key, body, {
      httpMetadata: { contentType },
    });
    return { key, etag: obj!.etag };
  }

  // 1. Initiate multipart upload
  const upload = await bucket.createMultipartUpload(key, {
    httpMetadata: { contentType },
  });

  try {
    // 2. Slice into parts
    const parts: ArrayBuffer[] = [];
    for (let offset = 0; offset < body.byteLength; offset += PART_SIZE_BYTES) {
      parts.push(body.slice(offset, offset + PART_SIZE_BYTES));
    }

    // 3. Upload parts in concurrent batches
    const completedParts: R2UploadedPart[] = [];
    for (let i = 0; i < parts.length; i += MAX_CONCURRENCY) {
      const batch = parts.slice(i, i + MAX_CONCURRENCY);
      const batchResults = await Promise.all(
        batch.map((part, batchIndex) =>
          upload.uploadPart(i + batchIndex + 1, part)
        )
      );
      completedParts.push(...batchResults);
    }

    // 4. Complete — R2 assembles parts in part number order
    const obj = await upload.complete(completedParts);
    return { key, etag: obj.etag };
  } catch (err) {
    // Abort to release incomplete part storage
    await upload.abort();
    throw err;
  }
}
```

## 2. Streaming Upload Without Full Buffering

For large uploads where buffering the entire body would exhaust memory, stream each part:

```typescript
// lib/r2-stream-multipart.ts

const CHUNK_SIZE = 10 * 1024 * 1024; // 10 MB
const CONCURRENCY = 4;

interface PendingPart {
  partNumber: number;
  data:       Uint8Array;
}

export async function streamingParallelUpload(
  bucket: R2Bucket,
  key: string,
  stream: ReadableStream<Uint8Array>,
  contentType: string
): Promise<string> {
  const upload = await bucket.createMultipartUpload(key, {
    httpMetadata: { contentType },
  });

  const completed: R2UploadedPart[] = [];
  const pending:   Promise<void>[]  = [];
  let partNumber = 1;
  let buffer     = new Uint8Array(0);

  const flushPart = async (part: PendingPart): Promise<void> => {
    const result = await upload.uploadPart(part.partNumber, part.data);
    completed[part.partNumber - 1] = result;
  };

  try {
    const reader = stream.getReader();

    while (true) {
      const { done, value } = await reader.read();

      if (value) {
        // Append chunk to buffer
        const merged = new Uint8Array(buffer.length + value.length);
        merged.set(buffer);
        merged.set(value, buffer.length);
        buffer = merged;
      }

      // Flush complete parts
      while (buffer.length >= CHUNK_SIZE || (done && buffer.length > 0)) {
        const slice = done
          ? buffer
          : buffer.slice(0, CHUNK_SIZE);
        buffer = done ? new Uint8Array(0) : buffer.slice(CHUNK_SIZE);

        const part: PendingPart = { partNumber: partNumber++, data: slice };
        pending.push(flushPart(part));

        // Throttle concurrency
        if (pending.length >= CONCURRENCY) {
          await Promise.all(pending.splice(0, CONCURRENCY));
        }
      }

      if (done) break;
    }

    // Flush remaining pending parts
    if (pending.length > 0) await Promise.all(pending);

    const obj = await upload.complete(completed.filter(Boolean));
    return obj.etag;
  } catch (err) {
    await upload.abort();
    throw err;
  }
}
```

## 3. Client-Coordinated Upload via Pre-Signed URLs

For browser uploads > 100 MB, avoid routing the data through the Worker at all. The Worker coordinates but the client uploads directly to R2:

```typescript
// worker.ts — coordination endpoint
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/upload/start" && request.method === "POST") {
      const { key, partCount, contentType } = await request.json<{
        key: string;
        partCount: number;
        contentType: string;
      }>();

      const upload = await env.R2.createMultipartUpload(key, {
        httpMetadata: { contentType },
      });

      // Return uploadId — client uses this to track the upload
      return Response.json({
        uploadId: upload.uploadId,
        key:      upload.objectName,
      });
    }

    if (url.pathname === "/upload/complete" && request.method === "POST") {
      const { key, uploadId, parts } = await request.json<{
        key:      string;
        uploadId: string;
        parts:    Array<{ partNumber: number; etag: string }>;
      }>();

      const upload = env.R2.resumeMultipartUpload(key, uploadId);
      const obj    = await upload.complete(parts);

      return Response.json({ etag: obj.etag, key: obj.key });
    }

    return new Response("Not Found", { status: 404 });
  },
};
```

## 4. Retry Logic for Individual Part Failures

```typescript
// lib/r2-part-retry.ts

export async function uploadPartWithRetry(
  upload: R2MultipartUpload,
  partNumber: number,
  data: ArrayBuffer,
  maxAttempts = 3
): Promise<R2UploadedPart> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await upload.uploadPart(partNumber, data);
    } catch (err) {
      if (attempt === maxAttempts) throw err;
      const backoffMs = 100 * Math.pow(2, attempt - 1); // 100ms, 200ms, 400ms
      await new Promise((r) => setTimeout(r, backoffMs));
    }
  }
  throw new Error(`uploadPartWithRetry: unreachable`);
}
```

## 5. Throughput Benchmark Helper

```typescript
// scripts/benchmark-upload.ts
export async function benchmarkUpload(
  bucket: R2Bucket,
  sizeBytes: number
): Promise<void> {
  const payload = new Uint8Array(sizeBytes).fill(0xab);

  // Single put
  const t0 = Date.now();
  await bucket.put("bench/single", payload);
  console.log(`Single put (${sizeBytes / 1e6} MB): ${Date.now() - t0} ms`);

  // Parallel multipart
  const { parallelUpload } = await import("./lib/r2-multipart");
  const t1 = Date.now();
  await parallelUpload(bucket, "bench/multipart", payload.buffer, "application/octet-stream");
  console.log(`Parallel multipart (${sizeBytes / 1e6} MB): ${Date.now() - t1} ms`);
}
```

## Anti-patterns

- **Uploading parts smaller than 5 MB** — R2 rejects parts below 5 MB (except the final part) with a 400 error. Always enforce a minimum part size.
- **Not calling `upload.abort()` on failure** — incomplete multipart uploads are stored at rest and incur storage charges until TTL expiry or explicit abort. Always abort in the catch block.
- **Using a single sequential `uploadPart` loop** — part uploads are independent and equally fast in parallel; sequential uploading is identical in speed to a single `put()` with none of the retry benefits.
- **Caching `uploadId` across Worker invocations without persistence** — upload IDs are opaque strings from R2 and do not expire immediately; store them in KV or D1 if the upload spans multiple requests.
- **Ignoring part order in `complete()`** — R2 assembles the object in part-number order, not the order parts appear in the `completedParts` array. Ensure the array is sorted by `partNumber` before calling `complete()`.

## Gotchas

- `R2MultipartUpload.uploadPart()` accepts `ArrayBuffer`, `ArrayBufferView`, `ReadableStream`, or `string`. Passing a `ReadableStream` streams the part body but does not support resumption within the part.
- Maximum part count is 10,000; for a 100 GB object that means a minimum part size of 10 MB. Plan part size to stay below the part-count ceiling.
- Workers have a 128 MB memory limit; do not buffer the full object before slicing. Use the streaming pattern (section 2) for objects > 50 MB.
- `resumeMultipartUpload()` does not re-fetch the list of already-uploaded parts — you must track them client-side (KV or D1) if implementing resumable uploads across multiple Worker invocations.
- R2 does not deduplicate parts uploaded with the same part number; re-uploading a part number overwrites the previous part for that slot.

## Verification

Use `wrangler r2 object get` to verify the final object and compare `ETag` with the expected multipart ETag (format: `<hash>-<partCount>`):

```bash
wrangler r2 object get my-bucket bench/multipart --local
# Check ETag header — multipart ETags end with -N where N is the part count
```

Target: for a 100 MB file with 10 × 10 MB parts and `CONCURRENCY = 6`, total upload wall time should be ≤ 2× single-part upload time for the same payload size.

## Related

- `r2-multipart-upload-performance.md`
- `r2-range-request-large-file-optimization.md`
- `r2-conditional-get-etag-bandwidth.md`
- `workers-subrequest-fanout-parallelism.md`
- `workers-streaming-large-payloads.md`

## Sources

- Cloudflare R2 Multipart Upload API — developers.cloudflare.com/r2/api/workers/workers-api-reference/#multipart-uploads
- S3 Multipart Upload limits — docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html
- Workers memory limits — developers.cloudflare.com/workers/platform/limits#memory
- R2 storage pricing — developers.cloudflare.com/r2/pricing
