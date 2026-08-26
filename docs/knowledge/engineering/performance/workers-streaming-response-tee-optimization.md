# Workers Streaming Response Tee Optimization

Date: 2026-08-23
Author: orkords.com
Status: production

## Symptom / Use-case

example project Workers serve large JSON feeds and LLM-generated content that must be (a) streamed to
the client immediately for low TTFB and (b) written to KV or R2 in parallel for caching and
audit-log purposes. The naive approach of buffering the entire response body before forking it
introduces a full-latency round-trip delay equivalent to downloading the entire payload before
the first byte reaches the user.

## Context

The Streams API `ReadableStream.tee()` method splits a single stream into two independent
streams without buffering the whole body. In Cloudflare Workers, `tee()` enables the Worker to
simultaneously stream the response to the caller and write a copy to a durable storage backend
(KV, R2, Queue) within the same request lifetime using `ctx.waitUntil`. This pattern is
essential for any write-through caching layer that cannot tolerate the double-latency of
buffer-then-write.

## Section 1 — Understand tee() Memory Semantics

`tee()` creates a backpressure-coupled copy: if one branch is consumed faster than the other,
the slower branch causes the internal buffer to grow. In Workers with a 128 MB memory cap,
an unbounded tee on a large R2 object can OOM the isolate.

```typescript
// src/lib/stream-diagnostics.ts
// Demonstrate tee buffer growth — for measurement only
export async function measureTeeBackpressure(
  sourceUrl: string
): Promise<{ clientMs: number; storeMs: number; maxBufferEstimateKB: number }> {
  const response = await fetch(sourceUrl);
  if (!response.body) throw new Error("No body");

  const [clientStream, storeStream] = response.body.tee();

  let totalBytes = 0;
  let storeBytes = 0;

  const clientStart = Date.now();
  // Simulate fast client consumption
  const clientReader = clientStream.getReader();
  while (true) {
    const { done, value } = await clientReader.read();
    if (done) break;
    totalBytes += value.byteLength;
  }
  const clientMs = Date.now() - clientStart;

  const storeStart = Date.now();
  // Simulate slow store write (e.g. KV put)
  const storeReader = storeStream.getReader();
  while (true) {
    const { done, value } = await storeReader.read();
    if (done) break;
    storeBytes += value.byteLength;
    // Simulate slow consumer
    await new Promise((r) => setTimeout(r, 1));
  }
  const storeMs = Date.now() - storeStart;

  return {
    clientMs,
    storeMs,
    // Buffer accumulates at the rate of (clientRate - storeRate)
    maxBufferEstimateKB: Math.ceil(totalBytes / 1024),
  };
}
```

For payloads over 1 MB with a slow storage consumer, set a size guard before teeing.

## Section 2 — Safe Tee Pattern for Feed Caching

The standard example project pattern: stream a D1 query result to the client while simultaneously
writing the serialised response into KV for the next request's cache hit.

```typescript
// src/lib/tee-to-kv.ts
interface TeeToKVOptions {
  kv: KVNamespace;
  cacheKey: string;
  ttlSeconds: number;
  maxCacheSizeBytes?: number; // default 512 KB; skip KV write above this
}

export function teeResponseToKV(
  responseBody: ReadableStream<Uint8Array>,
  ctx: ExecutionContext,
  opts: TeeToKVOptions
): ReadableStream<Uint8Array> {
  const { kv, cacheKey, ttlSeconds, maxCacheSizeBytes = 512 * 1024 } = opts;

  const [clientStream, storeStream] = responseBody.tee();

  // Background task: consume storeStream and write to KV
  ctx.waitUntil(
    (async () => {
      const chunks: Uint8Array[] = [];
      let totalBytes = 0;
      const reader = storeStream.getReader();

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          totalBytes += value.byteLength;

          if (totalBytes > maxCacheSizeBytes) {
            // Too large to cache — drain and bail
            reader.cancel("payload too large for KV cache");
            return;
          }
          chunks.push(value);
        }

        // Concatenate all chunks into a single ArrayBuffer
        const combined = new Uint8Array(totalBytes);
        let offset = 0;
        for (const chunk of chunks) {
          combined.set(chunk, offset);
          offset += chunk.byteLength;
        }

        await kv.put(cacheKey, combined.buffer, {
          expirationTtl: ttlSeconds,
          metadata: { cachedAt: Date.now(), size: totalBytes },
        });
      } catch (err) {
        // KV write failure must never break the client stream
        console.error("tee-to-kv write failed:", err);
      } finally {
        reader.releaseLock();
      }
    })()
  );

  // Return only the client-facing branch
  return clientStream;
}
```

Usage in a feed handler:

```typescript
// src/handlers/trending-feed.ts
import { teeResponseToKV } from "../lib/tee-to-kv.js";

export async function handleTrendingFeed(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const cacheKey = "trending:v1";

  // Try KV cache first
  const cached = await env.CACHE_KV.get(cacheKey, "arrayBuffer");
  if (cached) {
    return new Response(cached, {
      headers: { "Content-Type": "application/json", "X-Cache": "HIT" },
    });
  }

  // Build streaming response from D1
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const encoder = new TextEncoder();

  ctx.waitUntil(
    (async () => {
      const writer = writable.getWriter();
      const posts = await env.DB.prepare(
        "SELECT post_id, content, score FROM posts WHERE is_public=1 ORDER BY score DESC LIMIT 50"
      )
        .all()
        .then((r) => r.results);

      await writer.write(encoder.encode(JSON.stringify(posts)));
      await writer.close();
    })()
  );

  // Tee the stream: client gets clientStream, KV gets a copy via waitUntil
  const cachedStream = teeResponseToKV(readable, ctx, {
    kv: env.CACHE_KV,
    cacheKey,
    ttlSeconds: 30,
  });

  return new Response(cachedStream, {
    headers: { "Content-Type": "application/json", "X-Cache": "MISS" },
  });
}
```

## Section 3 — Tee to R2 for Audit Logging

For LLM-generated content subject to moderation review, tee the streamed AI response into R2
without buffering the client stream.

```typescript
// src/lib/tee-to-r2.ts
export function teeResponseToR2(
  body: ReadableStream<Uint8Array>,
  ctx: ExecutionContext,
  r2: R2Bucket,
  objectKey: string
): ReadableStream<Uint8Array> {
  const [clientStream, auditStream] = body.tee();

  ctx.waitUntil(
    (async () => {
      // R2 multipart upload for large audit logs; single put for < 5 MB
      try {
        await r2.put(objectKey, auditStream, {
          httpMetadata: { contentType: "application/json" },
          customMetadata: { timestamp: new Date().toISOString() },
        });
      } catch (err) {
        console.error(`r2 audit write failed for ${objectKey}:`, err);
        // Drain the audit stream to unblock the tee internal buffer
        const reader = auditStream.getReader();
        while (!(await reader.read()).done) { /* drain */ }
      }
    })()
  );

  return clientStream;
}
```

## Section 4 — TransformStream as a Tee Alternative for Transformation

When the stored copy needs transformation (e.g. stripping PII fields before KV cache),
use a `TransformStream` instead of `tee()` to avoid materialising both raw and transformed
copies simultaneously.

```typescript
// src/lib/redacting-tee.ts
export function teeWithRedaction(
  source: ReadableStream<Uint8Array>,
  ctx: ExecutionContext,
  kv: KVNamespace,
  cacheKey: string,
  redactFields: string[]
): ReadableStream<Uint8Array> {
  const [clientStream, rawStream] = source.tee();

  ctx.waitUntil(
    (async () => {
      const decoder = new TextDecoder();
      const encoder = new TextEncoder();
      const reader = rawStream.getReader();
      const chunks: string[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(decoder.decode(value, { stream: true }));
      }

      let json = chunks.join("");
      // Redact sensitive fields before caching
      for (const field of redactFields) {
        json = json.replace(
          new RegExp(`"${field}":\\s*"[^"]*"`, "g"),
          `"${field}":"[REDACTED]"`
        );
      }

      await kv.put(cacheKey, encoder.encode(json).buffer, {
        expirationTtl: 60,
      });
    })()
  );

  return clientStream; // raw (un-redacted) stream goes to client
}
```

## Anti-patterns

- Teeing without a `maxCacheSizeBytes` guard — a rogue large response can OOM the Worker
- Awaiting the store branch in the main response path — negates streaming benefit entirely
- Forgetting to drain the store branch on error — leaves the tee internal buffer growing,
  stalling the client stream via backpressure
- Using `tee()` on a `Request.body` and then passing both branches to `fetch()` — only one
  branch can be used as a fetch body; buffer the request if fan-out is needed
- Teeing inside a loop (creating O(n) stream copies) — tee once and pipe to n writers via
  `WritableStream` broadcasting

## Gotchas

- `ReadableStream.tee()` is specified to lock the original stream; the original reference is
  unusable after calling `tee()` — use only the two returned branches
- Workers `tee()` holds an in-memory buffer of the unread delta between branches;
  on large payloads the slower branch's backpressure can cause the Worker to exceed its
  128 MB memory limit before the response is complete
- `ctx.waitUntil` extends isolate lifetime past response delivery, but has a cap of 30 seconds
  total — very large R2 uploads may be cut off; use multipart for blobs > 5 MB
- R2 `put(key, stream)` does not support `Content-Length` from a tee branch because the length
  is unknown at stream start; R2 buffers internally until stream closes

## Verification

```bash
# Confirm client TTFB is streaming (first byte arrives before body completes)
curl -o /dev/null -s -w "TTFB: %{time_starttransfer}s  Total: %{time_total}s\n" \
  https://example.com/api/trending

# Verify KV write happened — check metadata.cachedAt is recent
npx wrangler kv key get "trending:v1" --namespace-id=<id> --metadata

# Workers memory usage — ensure tee buffer doesn't spike
# Workers > Analytics > Memory Usage p99 (compare before/after)
```

## Related

- `/documentation/docs/policies/performance/workers-streaming-large-payloads.md`
- `/documentation/docs/policies/performance/workers-response-streaming-ttfb-optimization.md`
- `/documentation/docs/policies/performance/workers-cache-api-stale-while-revalidate.md`
- `/documentation/docs/policies/performance/d1-query-result-caching-kv-workers.md`
- `/documentation/docs/policies/performance/r2-multipart-upload-performance.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/streams/readablestream/#tee
- https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream/tee
- https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/workers/platform/limits/#memory
