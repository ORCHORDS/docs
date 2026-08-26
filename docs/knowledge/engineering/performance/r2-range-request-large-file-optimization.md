# R2 Range Request Optimization for Large Files

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Workers endpoint that serves large video, audio, or binary files from R2 is causing high memory pressure and slow time-to-first-byte. Clients that support partial content (video players, download managers, resumable uploaders) are receiving full-file responses instead of the requested byte range. Streaming from R2 to the client stalls or OOMs the Worker.

## Context

Cloudflare R2 supports the standard HTTP `Range` header when accessed through the S3-compatible API or the native R2 binding. A Worker sitting in front of R2 must explicitly forward the `Range` header from the client to the R2 `get()` call and correctly synthesise a `206 Partial Content` response with a matching `Content-Range` header. Failing to do so forces the Worker to fetch the entire object, blowing through the 128 MB Worker memory limit and delaying playback start.

## Parsing and Forwarding Range Headers

```typescript
interface Env {
  BUCKET: R2Bucket;
}

function parseRange(
  rangeHeader: string | null,
  objectSize: number
): { offset: number; length: number } | null {
  if (!rangeHeader) return null;

  // Handle "bytes=START-END" and "bytes=START-" (open-ended)
  const match = rangeHeader.match(/^bytes=(\d+)-(\d*)$/);
  if (!match) return null;

  const start = parseInt(match[1], 10);
  const end = match[2] ? parseInt(match[2], 10) : objectSize - 1;

  if (start > end || end >= objectSize) return null;
  return { offset: start, length: end - start + 1 };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1); // strip leading "/"

    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // HEAD request: return metadata without body
    if (request.method === "HEAD") {
      const object = await env.BUCKET.head(key);
      if (!object) return new Response(null, { status: 404 });
      return new Response(null, {
        status: 200,
        headers: {
          "Content-Length": String(object.size),
          "Accept-Ranges": "bytes",
          "ETag": object.httpEtag,
          "Last-Modified": object.uploaded.toUTCString(),
        },
      });
    }

    const rangeHeader = request.headers.get("Range");

    // Fetch HEAD first to know the object size without downloading the body
    const meta = await env.BUCKET.head(key);
    if (!meta) return new Response("Not Found", { status: 404 });

    const range = parseRange(rangeHeader, meta.size);

    // Partial content path
    if (range) {
      const object = await env.BUCKET.get(key, {
        range: { offset: range.offset, length: range.length },
      });
      if (!object) return new Response("Not Found", { status: 404 });

      const end = range.offset + range.length - 1;
      return new Response(object.body, {
        status: 206,
        headers: {
          "Content-Range": `bytes ${range.offset}-${end}/${meta.size}`,
          "Content-Length": String(range.length),
          "Content-Type": meta.httpMetadata?.contentType ?? "application/octet-stream",
          "Accept-Ranges": "bytes",
          "ETag": meta.httpEtag,
          "Cache-Control": "public, max-age=3600",
        },
      });
    }

    // Full-file path — stream directly, never buffer in memory
    const object = await env.BUCKET.get(key);
    if (!object) return new Response("Not Found", { status: 404 });

    return new Response(object.body, {
      status: 200,
      headers: {
        "Content-Length": String(meta.size),
        "Content-Type": meta.httpMetadata?.contentType ?? "application/octet-stream",
        "Accept-Ranges": "bytes",
        "ETag": meta.httpEtag,
        "Cache-Control": "public, max-age=3600",
      },
    });
  },
};
```

## Caching Partial Responses at the Edge

```typescript
// Cloudflare's shared cache stores 206 responses keyed on URL + Range.
// Use cf.cacheEverything and set a stable cache key to maximise reuse.

async function fetchWithRangeCache(
  request: Request,
  key: string,
  env: Env
): Promise<Response> {
  // Normalise cache key: URL + canonical range string
  const rangeHeader = request.headers.get("Range") ?? "bytes=0-";
  const cacheUrl = `${request.url}|range=${rangeHeader}`;
  const cacheKey = new Request(cacheUrl, { method: "GET" });

  const cached = await caches.default.match(cacheKey);
  if (cached) return cached;

  // Cache miss: fetch from R2 (handled by main fetch handler)
  const response = await fetch(request);
  if (response.status === 206) {
    // Clone before consuming body — cache the clone
    const toCache = response.clone();
    // waitUntil not available here; use ctx.waitUntil at call site
    await caches.default.put(cacheKey, toCache);
  }
  return response;
}
```

## Multipart Range Requests

```typescript
// Some HTTP clients send multi-range: "bytes=0-499,600-999"
// R2 does not natively support multipart ranges; synthesise multipart/byteranges manually.

async function serveMultipartRange(
  ranges: Array<{ offset: number; length: number }>,
  object: R2Object & { body: ReadableStream },
  totalSize: number,
  contentType: string
): Promise<Response> {
  const boundary = crypto.randomUUID().replace(/-/g, "");
  const parts: string[] = [];

  for (const r of ranges) {
    const end = r.offset + r.length - 1;
    parts.push(
      `--${boundary}\r\n` +
      `Content-Type: ${contentType}\r\n` +
      `Content-Range: bytes ${r.offset}-${end}/${totalSize}\r\n\r\n`
    );
    // In production: pipe individual range reads here
  }
  parts.push(`--${boundary}--\r\n`);

  // Simplified: return boundary structure for single-range fallback
  return new Response(parts.join(""), {
    status: 206,
    headers: {
      "Content-Type": `multipart/byteranges; boundary=${boundary}`,
    },
  });
}
```

## Anti-patterns

- Calling `env.BUCKET.get(key)` without a `range` option when the client sent a `Range` header — this fetches the entire file and wastes CPU time, memory, and egress cost.
- Buffering the R2 body with `await object.arrayBuffer()` before streaming — always pass `object.body` (a `ReadableStream`) directly to the `Response` constructor.
- Returning `200 OK` instead of `206 Partial Content` when a range was served — media players use the status code to detect resumability and seek accuracy.

## Gotchas

- `env.BUCKET.head()` counts as a Class A operation (billed); for high-traffic endpoints, cache the object metadata in Workers KV with a short TTL instead of calling `head()` on every request.
- R2 `get()` with a `range` option that exceeds the object size returns `null` rather than an error — validate the range bounds against `meta.size` before calling `get()`.

## Verification

```bash
# Confirm 206 response and correct Content-Range header
curl -v -H "Range: bytes=0-1023" "https://cdn.example.com/videos/intro.mp4" 2>&1 \
  | grep -E "< HTTP|< Content-Range|< Content-Length|< Accept-Ranges"

# Test open-ended range (common for video seek-to-end)
curl -v -H "Range: bytes=10485760-" "https://cdn.example.com/videos/intro.mp4" 2>&1 \
  | grep -E "< HTTP|< Content-Range"

# Measure TTFB for a range request vs full-file request
hyperfine --warmup 3 \
  'curl -s -H "Range: bytes=0-65535" -o /dev/null -w "%{time_starttransfer}" https://cdn.example.com/videos/intro.mp4' \
  'curl -s -o /dev/null -w "%{time_starttransfer}" https://cdn.example.com/videos/intro.mp4'
```

## Related

- `performance/r2-multipart-upload-performance.md`
- `performance/cloudflare-r2-presigned-cdn-acceleration.md`
- `performance/http-range-resume-validator-contract.md`
- `performance/workers-streaming-large-payloads.md`

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/#r2bucketget
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/#ranged-reads
- https://www.rfc-editor.org/rfc/rfc9110#section-14
