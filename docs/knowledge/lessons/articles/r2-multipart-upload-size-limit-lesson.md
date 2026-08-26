# R2 Single-Part Upload Limit Caused Silent Failures for Large Exports

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Users exporting large dataset snapshots from the example project analytics dashboard started receiving a generic "Export failed, please try again" error for any file larger than roughly 100 MB. Smaller exports completed normally. The error surfaced intermittently in Sentry with no accompanying R2 error code — only a `fetch failed` message from the Worker — making it appear as a transient network issue. Three days passed before the pattern was connected to file size.

## Context

The example project platform generates user-facing data exports (CSV, Parquet, JSON) from an analytics pipeline Worker. Files are assembled in memory, then written to R2 in a single `env.EXPORTS_BUCKET.put()` call before a signed URL is returned to the frontend. This pattern worked reliably during development and staging because test exports were synthetically small. The R2 bucket had no lifecycle or size policies configured. The export Worker allocated the full dataset into a `Uint8Array` before writing, meaning large exports also risked exhausting the 128 MB Worker memory limit.

## Timeline

- **Day 1, 11:05 UTC** – First customer support ticket: "My export keeps failing for the quarterly report." Support closes ticket as transient; asks user to retry.
- **Day 1, 14:20 UTC** – Second identical ticket from a different enterprise customer. Retry does not help.
- **Day 2, 09:45 UTC** – Engineer notices Sentry error cluster: 47 `fetch failed` events tagged to the export endpoint over 48 hours.
- **Day 2, 10:30 UTC** – Local reproduction attempted with a 150 MB test payload; `env.EXPORTS_BUCKET.put()` throws with no useful message in the Miniflare environment.
- **Day 2, 11:00 UTC** – Cloudflare documentation reviewed; R2 single-part upload limit is **5 GB per object** — that is not the problem. Developer notices the **Worker subrequest body size** limit is **300 MB**, but the actual failure is traced to `R2Object.put()` with a `ReadableStream` that the Worker exhausted into memory before calling put, triggering the 128 MB memory OOM, not an R2 limit per se.
- **Day 2, 12:15 UTC** – Root cause confirmed: for objects above ~85 MB the Worker runs out of heap before writing to R2. The `fetch failed` error is the Worker crashing mid-export.
- **Day 2, 14:00 UTC** – Emergency change: switch large exports to the R2 multipart upload API with 8 MB parts, streamed directly from the pipeline without buffering the full object.
- **Day 2, 16:30 UTC** – Deploy verified with a 500 MB synthetic export; completes in 12 seconds. Customer exports resume.
- **Day 3, 09:00 UTC** – Retro held, monitoring and size-based routing added.

## Root Cause

The export Worker buffered the entire dataset into a single in-memory `ArrayBuffer` before calling `env.EXPORTS_BUCKET.put()`. For exports above approximately 85 MB (leaving headroom for Worker runtime overhead), the V8 heap was exhausted and the Worker crashed. The error surface was opaque because the OOM manifested as an unhandled rejection with the message `fetch failed` rather than an explicit memory error. No size-based routing existed to switch larger payloads to a streaming or chunked write path. The R2 multipart upload API, which is designed exactly for this use-case, was never considered during the initial implementation.

## Fix: Multipart Upload for Large R2 Objects

The fix splits exports into 8 MB parts using the R2 multipart upload API, streaming data from the pipeline without ever holding the full object in memory simultaneously.

```typescript
// src/exports/r2-writer.ts

const MULTIPART_THRESHOLD_BYTES = 50 * 1024 * 1024; // 50 MB
const PART_SIZE_BYTES = 8 * 1024 * 1024; // 8 MB — R2 minimum part size is 5 MB

export async function writeExportToR2(
  bucket: R2Bucket,
  key: string,
  dataStream: ReadableStream<Uint8Array>,
  contentType: string
): Promise<void> {
  // Peek at first chunk to decide routing
  const reader = dataStream.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  let firstRead = true;

  // Buffer up to the threshold before deciding
  while (totalBytes < MULTIPART_THRESHOLD_BYTES) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    totalBytes += value.byteLength;
    firstRead = false;
  }

  // Re-read remaining stream
  const remainingStream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      // Pump the rest of the original reader
      async function pump() {
        while (true) {
          const { done, value } = await reader.read();
          if (done) { controller.close(); return; }
          controller.enqueue(value);
        }
      }
      pump().catch(e => controller.error(e));
    }
  });

  const { done: streamEnded } = await reader.read().catch(() => ({ done: true, value: undefined }));

  if (totalBytes < MULTIPART_THRESHOLD_BYTES && (streamEnded || firstRead)) {
    // Small file — single-part put is fine
    const combined = mergeChunks(chunks, totalBytes);
    await bucket.put(key, combined, { httpMetadata: { contentType } });
    return;
  }

  // Large file — use multipart API
  await multipartWrite(bucket, key, contentType, chunks, reader);
}

async function multipartWrite(
  bucket: R2Bucket,
  key: string,
  contentType: string,
  bufferedChunks: Uint8Array[],
  reader: ReadableStreamDefaultReader<Uint8Array>
): Promise<void> {
  const upload = await bucket.createMultipartUpload(key, {
    httpMetadata: { contentType },
  });

  const parts: R2UploadedPart[] = [];
  let partBuffer: Uint8Array[] = [...bufferedChunks];
  let partBufferSize = bufferedChunks.reduce((s, c) => s + c.byteLength, 0);
  let partNumber = 1;

  async function flushPart() {
    const partData = mergeChunks(partBuffer, partBufferSize);
    const part = await upload.uploadPart(partNumber, partData);
    parts.push(part);
    partNumber++;
    partBuffer = [];
    partBufferSize = 0;
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      partBuffer.push(value);
      partBufferSize += value.byteLength;
      if (partBufferSize >= PART_SIZE_BYTES) {
        await flushPart();
      }
    }
    // Flush remainder (may be smaller than PART_SIZE_BYTES — that is fine for the last part)
    if (partBufferSize > 0) {
      await flushPart();
    }
    await upload.complete(parts);
  } catch (err) {
    await upload.abort();
    throw err;
  }
}

function mergeChunks(chunks: Uint8Array[], totalBytes: number): Uint8Array {
  const out = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out;
}
```

## Prevention Checklist

- [ ] Never buffer arbitrary user-driven payloads into a single `ArrayBuffer` in a Worker; always stream large writes through multipart R2 uploads.
- [ ] Set a Worker memory budget check in load tests: exports at 50 MB, 100 MB, 250 MB, and 500 MB must all complete without OOM.
- [ ] Add an export file size estimate before starting the pipeline; reject requests estimated above 2 GB with a human-readable message rather than crashing.
- [ ] Configure a Cloudflare logpush alert for Worker `exceeded memory limit` errors — these fire as a distinct error class.
- [ ] Document the multipart threshold constant in the codebase and the R2 minimum part size (5 MB) so future engineers do not accidentally set parts too small.

## Monitoring Gaps Identified

- Worker OOM crashes produced only a generic `fetch failed` signal in Sentry with no memory context, delaying root-cause identification by nearly two days.
- No export file-size histogram existed; the team had no data showing that export sizes were growing month-over-month, which would have predicted this incident.

## Anti-patterns

- Using `R2Bucket.put()` for objects of unbounded size without verifying the size fits within Worker memory constraints.
- Assuming that a pattern working in staging is production-safe without load-testing it at realistic data volumes.
- Surfacing OOM errors as opaque network failures to the end-user without any size or memory context in internal logs.

## Gotchas

- R2 multipart upload requires a **minimum part size of 5 MB** for all parts except the last; uploading smaller parts returns an error. Set your part size constant to at least 5 MiB plus a margin.
- `upload.abort()` must be called in the catch block if any part upload fails; otherwise the in-progress multipart upload occupies R2 storage indefinitely until the 7-day automatic expiry.
- Workers CPU time limit (30 seconds for paid plans, 30 ms burst for free) can be hit during large multipart uploads if chunk processing is CPU-intensive; offload CPU work to a Durable Object or Queue if needed.

## Verification

```bash
# Generate a 200 MB synthetic export payload
dd if=/dev/urandom bs=1M count=200 | base64 > /tmp/test-export-200mb.txt

# Upload via the export endpoint (replace with your staging URL)
curl -X POST https://example project-staging.workers.dev/api/export \
  -H "Authorization: Bearer $example project_TEST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"dataset":"orders","format":"csv","range":"2025-Q4"}' \
  -o /tmp/export-result.json

# Check the returned signed URL and download size
jq -r '.downloadUrl' /tmp/export-result.json | xargs curl -sI | grep content-length

# Confirm no multipart upload leaks in the bucket (should be empty list)
npx wrangler r2 object list example project_EXPORTS --prefix=multipart-tmp/ --env production
```

## Related

- `lessons/r2-eventual-consistency-cache-invalidation-incident.md`
- `lessons/logpush-r2-backpressure-dropped-observability.md`
- `lessons/cloudflare-storage-primitive-selection.md`

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/#multipart-upload
- https://developers.cloudflare.com/workers/platform/limits/#memory
- https://developers.cloudflare.com/r2/objects/multipart-objects/
- https://developers.cloudflare.com/workers/runtime-apis/streams/
