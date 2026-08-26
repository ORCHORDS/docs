# R2 Multipart Download Parallel Chunk Assembly

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker serves large files (video, ZIP archives, ML model weights) from R2. Single-stream
download throughput is capped by the latency×bandwidth product of one TCP connection between
the Worker and the R2 bucket. For files over ~50 MB, splitting the fetch into parallel byte
range requests and streaming the assembled result reduces time-to-first-byte and total
transfer time for the end client, particularly when the Worker is co-located with R2 but
the client connection is the bottleneck.

---

## Context

R2 supports HTTP Range requests (`Range: bytes=start-end`). A Worker can issue N parallel
sub-range fetches against the same R2 object, buffer each chunk as it arrives, and pipe the
assembled byte stream to the client as a single `ReadableStream`. This technique mirrors the
multi-part download used by download managers and `aria2c`.

Unlike `r2-multipart-parallel-upload-throughput.md` (which covers the Multipart Upload API
for writing large objects), this article covers the **read path**: parallelising GET requests
to reduce latency.

When to use:
- File sizes 50 MB – several GB served from a Worker
- Clients that do not support or do not negotiate Range requests themselves
- Workers that need to transform (decrypt, decompress, transcode) each chunk before
  forwarding — parallelism hides transform latency

When NOT to use:
- Files < 10 MB: R2 single-stream saturates available bandwidth; overhead exceeds gain
- Streaming responses where the first byte must arrive immediately (use direct single-range)
- If the client already sends a `Range` header: honour it directly rather than
  re-splitting (see Gotchas)

---

## Fetching object metadata to plan chunk boundaries

```typescript
interface ChunkPlan {
  objectKey: string;
  totalBytes: number;
  chunkSize: number;
  chunks: Array<{ start: number; end: number }>;
}

async function buildChunkPlan(
  bucket: R2Bucket,
  key: string,
  chunkSizeBytes = 8 * 1024 * 1024 // 8 MB chunks
): Promise<ChunkPlan> {
  const head = await bucket.head(key);
  if (!head) throw new Response('Not Found', { status: 404 });

  const total = head.size;
  const chunks: Array<{ start: number; end: number }> = [];
  for (let start = 0; start < total; start += chunkSizeBytes) {
    chunks.push({ start, end: Math.min(start + chunkSizeBytes - 1, total - 1) });
  }
  return { objectKey: key, totalBytes: total, chunkSize: chunkSizeBytes, chunks };
}
```

---

## Parallel chunk fetch with controlled concurrency

Unlimited parallelism would exhaust the Worker's subrequest quota (1 000 subrequests per
request). Use a semaphore to cap concurrent R2 fetches.

```typescript
async function fetchChunk(
  bucket: R2Bucket,
  key: string,
  start: number,
  end: number
): Promise<Uint8Array> {
  const obj = await bucket.get(key, { range: { offset: start, length: end - start + 1 } });
  if (!obj) throw new Error(`R2 object not found: ${key}`);
  return new Uint8Array(await obj.arrayBuffer());
}

async function parallelFetch(
  bucket: R2Bucket,
  plan: ChunkPlan,
  maxConcurrency = 6
): Promise<Uint8Array[]> {
  const results: Uint8Array[] = new Array(plan.chunks.length);
  let idx = 0;

  async function worker(): Promise<void> {
    while (idx < plan.chunks.length) {
      const myIdx = idx++;
      const { start, end } = plan.chunks[myIdx];
      results[myIdx] = await fetchChunk(bucket, plan.objectKey, start, end);
    }
  }

  // Spin up maxConcurrency workers
  await Promise.all(Array.from({ length: maxConcurrency }, worker));
  return results;
}
```

---

## Streaming assembly via TransformStream

Rather than buffering the entire file in memory (hitting the Worker's 128 MB limit),
pipe chunks into a `TransformStream` as soon as each arrives *in order*.

```typescript
function assembleStream(
  bucket: R2Bucket,
  plan: ChunkPlan,
  maxConcurrency = 6
): ReadableStream<Uint8Array> {
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>();
  const writer = writable.getWriter();

  (async () => {
    try {
      // Pre-fetch next chunks while writing current one
      const inFlight = new Map<number, Promise<Uint8Array>>();

      function prefetch(i: number): void {
        if (i < plan.chunks.length && !inFlight.has(i)) {
          const { start, end } = plan.chunks[i];
          inFlight.set(i, fetchChunk(bucket, plan.objectKey, start, end));
        }
      }

      // Seed the pipeline
      for (let i = 0; i < Math.min(maxConcurrency, plan.chunks.length); i++) {
        prefetch(i);
      }

      for (let i = 0; i < plan.chunks.length; i++) {
        prefetch(i + maxConcurrency); // keep pipeline full
        const chunk = await inFlight.get(i)!;
        inFlight.delete(i);
        await writer.write(chunk);
      }
      await writer.close();
    } catch (err) {
      await writer.abort(err);
    }
  })();

  return readable;
}
```

---

## Complete Worker handler

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.slice(1); // strip leading /

    if (!key) return new Response('Missing key', { status: 400 });

    // If client sent a Range header, honour it directly — no need to re-chunk
    if (request.headers.has('Range')) {
      const obj = await env.BUCKET.get(key, {
        range: request.headers,
      });
      if (!obj) return new Response('Not Found', { status: 404 });
      return new Response(obj.body, {
        status: 206,
        headers: {
          'Content-Range': `bytes */${obj.size}`,
          'Content-Type': obj.httpMetadata?.contentType ?? 'application/octet-stream',
          ETag: obj.httpEtag,
        },
      });
    }

    const plan = await buildChunkPlan(env.BUCKET, key);
    const stream = assembleStream(env.BUCKET, plan);

    return new Response(stream, {
      status: 200,
      headers: {
        'Content-Length': String(plan.totalBytes),
        'Content-Type': 'application/octet-stream',
        'Accept-Ranges': 'bytes',
        'X-Chunk-Count': String(plan.chunks.length),
        'Cache-Control': 'public, max-age=3600',
      },
    });
  },
};
```

---

## Tuning chunk size vs. concurrency

| File Size | Recommended Chunk | Concurrency | Notes                              |
|-----------|------------------|-------------|------------------------------------|
| < 10 MB   | Single request   | 1           | No benefit from splitting          |
| 10–100 MB | 8 MB             | 4           | Balances subrequest count and fill |
| 100 MB–1 GB | 16 MB          | 6           | Saturates Worker → R2 bandwidth    |
| > 1 GB    | 32 MB            | 6–8         | Monitor 128 MB heap limit          |

Workers have a 30-second CPU time limit; for very large files consider offloading the
assembly to a Durable Object with a longer lifetime, or using a presigned R2 URL to let
the client download directly.

---

## Anti-patterns

- **Buffering all chunks before streaming.** Fully materialising a 200 MB file in Worker
  memory will hit the 128 MB heap limit. Always stream via `TransformStream`.
- **Unlimited concurrency.** Each `bucket.get()` call counts as a subrequest (limit: 1 000
  per request). With 32 MB chunks a 1 GB file needs 32 chunks; well within limits, but
  a poorly-chosen small chunk size can exhaust quota.
- **Re-splitting a client Range request.** If the client sends `Range: bytes=0-1023`,
  honour it directly rather than splitting it — the client knows what it wants.
- **Ignoring ETag on parallel fetches.** R2 may serve different versions of a mutable
  object during a deploy. Validate ETags on all chunks against the head response.

---

## Gotchas

- R2 does not charge for internal Worker ↔ R2 egress within the same Cloudflare account,
  but each `bucket.get()` call counts as a Class B operation (billed per 1 000).
- The `range.length` parameter in `bucket.get()` is the number of bytes, not the end
  offset; use `end - start + 1`.
- `TransformStream` back-pressure is cooperative: if the client reads slowly, `writer.write`
  will await the downstream drain before accepting more data, which naturally throttles the
  prefetch pipeline.
- Workers streaming responses are subject to a 100 MB response body limit in some
  configurations — verify with `wrangler dev` against real file sizes before production
  deployment.

---

## Verification

```bash
# Compare single-stream vs. parallel-chunk download time
time curl -o /dev/null https://your-worker.workers.dev/large-file.zip

# Inspect chunk count in response headers
curl -I https://your-worker.workers.dev/large-file.zip | grep X-Chunk-Count

# Confirm Range passthrough works for partial content
curl -H "Range: bytes=0-1023" -I https://your-worker.workers.dev/large-file.zip
# Expect: HTTP/1.1 206 Partial Content
```

---

## Related

- `r2-multipart-parallel-upload-throughput.md`
- `r2-range-request-large-file-optimization.md`
- `cloudflare-r2-presigned-cdn-acceleration.md`
- `workers-streaming-large-payloads.md`
- `workers-subrequest-fanout-parallelism.md`

---

## Sources

- R2 Workers API — range: https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Workers subrequest limits: https://developers.cloudflare.com/workers/platform/limits/#subrequests
- TransformStream API: https://developers.cloudflare.com/workers/runtime-apis/streams/transformstream/
