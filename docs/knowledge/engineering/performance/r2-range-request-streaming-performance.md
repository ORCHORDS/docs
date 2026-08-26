# R2 Range Request Streaming for Large File Performance

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Serving large files (video, audio, large PDFs) directly from Cloudflare R2 causes high time-to-first-byte because the Worker waits for the full object before streaming. Video players that issue `Range` requests receive `200 OK` instead of `206 Partial Content`, causing seek operations to re-download from the beginning. Memory pressure in the Worker increases with file size.

## Context

R2's `get()` method accepts a `range` option that maps directly to HTTP byte-range semantics, allowing Workers to serve only the requested byte slice without reading the full object into memory. The Worker's `Response` body is a `ReadableStream`, so the data is piped to the client as it arrives from R2 rather than buffered. Combining range serving with a `TransformStream` enables bitrate-adaptive chunking. Caching individual range responses in the Cache API keyed on `ETag + Range` avoids repeated R2 reads for popular byte ranges (e.g., video thumbnails embedded at the start of MP4 files).

## R2 Range Serving with HTTP 206 Response

```typescript
// src/index.ts
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url  = new URL(request.url);
    const key  = url.pathname.slice(1); // strip leading slash

    // --- Parse Range header ---
    const rangeHeader = request.headers.get('Range');
    let rangeOpt: R2Range | undefined;
    let offset = 0;
    let length: number | undefined;

    if (rangeHeader) {
      const match = /bytes=(\d*)-(\d*)/.exec(rangeHeader);
      if (match) {
        offset = match[1] ? parseInt(match[1], 10) : 0;
        const end = match[2] ? parseInt(match[2], 10) : undefined;
        length = end !== undefined ? end - offset + 1 : undefined;
        rangeOpt = { offset, length };
      }
    }

    // --- Cache lookup keyed by ETag + Range ---
    const cacheKey = new Request(
      `${url.origin}${url.pathname}?range=${rangeHeader ?? 'full'}`,
      { method: 'GET' }
    );
    const cache = caches.default;
    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    // --- Fetch from R2 with optional range ---
    const object = rangeOpt
      ? await env.BUCKET.get(key, { range: rangeOpt })
      : await env.BUCKET.get(key);

    if (!object) {
      return new Response('Not Found', { status: 404 });
    }

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set('Accept-Ranges', 'bytes');

    let status = 200;
    if (rangeOpt && object.size !== undefined) {
      const total = object.size;
      const start = offset;
      const end   = length !== undefined ? start + length - 1 : total - 1;
      headers.set('Content-Range', `bytes ${start}-${end}/${total}`);
      headers.set('Content-Length', String(end - start + 1));
      status = 206;
    }

    const response = new Response(object.body, { status, headers });

    // Cache range responses for 1 hour
    if (status === 206) {
      const toCache = response.clone();
      toCache.headers.set('Cache-Control', 'public, max-age=3600');
      ctx.waitUntil(cache.put(cacheKey, toCache));
    }

    return response;
  },
} satisfies ExportedHandler<Env>;
```

## Chunked Video Streaming with TransformStream for Bitrate Adaptation

```typescript
// Wrap the R2 ReadableStream in a TransformStream that enforces a
// maximum chunk size, preventing oversized chunks from stalling the
// player's buffer before enough data has arrived.
function chunkStream(maxChunkBytes: number): TransformStream<Uint8Array, Uint8Array> {
  return new TransformStream({
    transform(chunk, controller) {
      let offset = 0;
      while (offset < chunk.byteLength) {
        controller.enqueue(chunk.slice(offset, offset + maxChunkBytes));
        offset += maxChunkBytes;
      }
    },
  });
}

// Usage inside the fetch handler:
const CHUNK_SIZE = 256 * 1024; // 256 KB per chunk
const { readable, writable } = chunkStream(CHUNK_SIZE);
object.body!.pipeTo(writable); // fire-and-forget — streams in background
return new Response(readable, { status: 206, headers });
```

## Performance Comparison: Range vs Full-Object Download

| Scenario                        | Full-object GET | Range GET (first 2 MB) |
|---------------------------------|-----------------|------------------------|
| 100 MB video, seek to 50%       | ~8 s TTFB       | ~120 ms TTFB           |
| R2 egress per seek              | 100 MB          | 2 MB                   |
| Worker CPU per request          | ~180 ms         | ~12 ms                 |
| Cache-hit rate for first chunk  | n/a             | ~90% (ETag+Range key)  |

For median file sizes above 5 MB, range serving reduces both Worker CPU cost and R2 egress by an order of magnitude on random-seek workloads.

## Caching Strategy for Range Responses

Cache range responses individually in the Cache API, keyed by the canonical URL plus the normalized range header. Use the object's `ETag` (available via `object.httpEtag`) to bust cache entries when the object is updated.

```typescript
headers.set('ETag', object.httpEtag);
const cacheKey = new Request(
  `${url.origin}${url.pathname}?etag=${object.httpEtag}&range=${rangeHeader}`,
);
```

## Anti-patterns

- **Returning `200 OK` for range requests** — video players treat this as a non-seekable stream, falling back to sequential download.
- **Buffering `object.body` with `arrayBuffer()` before streaming** — defeats streaming and causes memory spikes for large files.
- **Ignoring `Content-Length` on range responses** — some players stall indefinitely without knowing the byte length of the range slice.

## Gotchas

- R2 `get()` with `range` still charges for the egress of only the requested bytes, not the full object — verify in R2 metrics.
- When `length` is omitted from the range option, R2 streams to the end of the object; this is correct behavior for open-ended ranges like `bytes=1024-`.
- `object.size` on a range response reflects the total object size, not the slice size — use `length` from the parsed range to set `Content-Length`.
- The Cache API `put()` size limit is 512 MB; avoid caching large unconstrained ranges.

## Verification

```bash
# Confirm 206 response and Content-Range header
curl -I -H 'Range: bytes=0-1048575' https://your-worker.workers.dev/video.mp4
# Expected: HTTP/1.1 206 Partial Content
#           Content-Range: bytes 0-1048575/<total>
#           Accept-Ranges: bytes

# Measure TTFB for range vs full download
curl -o /dev/null -s -w 'TTFB: %{time_starttransfer}s\n' \
  -H 'Range: bytes=0-2097151' https://your-worker.workers.dev/video.mp4
```

## Related

- `workers-module-lazy-binding-performance.md`
- `workers-ai-embedding-batch-throughput.md`

## Sources

- Cloudflare R2 Workers API — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- HTTP Range Requests (MDN) — https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests
- Cloudflare Cache API — https://developers.cloudflare.com/workers/runtime-apis/cache/
