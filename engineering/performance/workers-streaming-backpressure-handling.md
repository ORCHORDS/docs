# Workers Streaming Response Backpressure Handling

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker streams a large upstream body (S3/R2 object, AI token stream, database cursor) to
the client. Under slow or lossy network conditions, the Worker buffers unboundedly, CPU time spikes,
and the isolate may be terminated with a `Worker exceeded CPU limit` or silent response truncation.

---

## Context

Workers ship a WHATWG Streams implementation with backpressure signals built into
`ReadableStreamBYOBReader` and the `WritableStream` internal queue. However, the plumbing must be
explicit: piping through a `TransformStream` does **not** automatically pause the readable side when
the client's TCP receive window fills. You must honour the writable stream's `desiredSize` and `ready`
promise to avoid runaway buffering inside the isolate.

---

## Mechanism: `pipeTo` with Automatic Backpressure

The simplest correct pattern uses `ReadableStream.pipeTo(writable)`. The Streams spec requires the
pipe algorithm to pause pulling from the readable when the writable's queue fills.

```typescript
export default {
  async fetch(request: Request): Promise<Response> {
    const upstream = await fetch('https://storage.example.com/large-file');
    if (!upstream.body) return new Response('no body', { status: 502 });

    // pipeTo respects backpressure automatically.
    // The client-facing TransformStream connects readable to response.
    const { readable, writable } = new TransformStream();
    upstream.body.pipeTo(writable); // fire-and-forget; backpressure flows upstream

    return new Response(readable, {
      headers: upstream.headers,
    });
  },
};
```

`pipeTo` does not need `await` — the pipe runs concurrently with the caller receiving the
`Response`. The internal backpressure prevents the upstream fetch from outrunning the client.

---

## Manual Backpressure with `desiredSize`

When chunk-level logic is needed (e.g., token counting, line splitting), use a manual pull loop
that checks `WritableStreamDefaultWriter.desiredSize` before writing.

```typescript
async function relayWithBackpressure(
  readable: ReadableStream<Uint8Array>,
  writable: WritableStream<Uint8Array>,
): Promise<void> {
  const reader = readable.getReader();
  const writer = writable.getWriter();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // Honour the writable's queue pressure before writing.
      if ((writer.desiredSize ?? 1) <= 0) {
        await writer.ready; // yield until the consumer drains
      }

      await writer.write(value);
    }
    await writer.close();
  } catch (err) {
    await writer.abort(err);
  } finally {
    reader.releaseLock();
    writer.releaseLock();
  }
}
```

---

## Bounded TransformStream Queue Size

By default `TransformStream` uses a chunk-count `highWaterMark` of 1. For byte streams,
configure a byte-length queing strategy so the backpressure threshold is in bytes, not chunks.

```typescript
const byteStrategy = new ByteLengthQueuingStrategy({ highWaterMark: 64 * 1024 }); // 64 KiB

const { readable, writable } = new TransformStream(
  {
    transform(chunk, controller) {
      // optional processing
      controller.enqueue(chunk);
    },
  },
  new ByteLengthQueuingStrategy({ highWaterMark: 256 * 1024 }), // writable side
  byteStrategy, // readable side
);
```

Keeping both sides at 64–256 KiB caps total in-flight memory to ~512 KiB per stream per isolate.

---

## Abort Handling on Client Disconnect

When the client disconnects mid-stream the response `WritableStream` is errored. Without explicit
abort propagation the upstream fetch continues consuming bandwidth.

```typescript
export default {
  async fetch(request: Request): Promise<Response> {
    const controller = new AbortController();
    const upstream = await fetch('https://origin.example.com/stream', {
      signal: controller.signal,
    });

    const { readable, writable } = new TransformStream();

    upstream.body!
      .pipeTo(writable)
      .catch(() => controller.abort()); // upstream cancelled when pipe errors

    // If the response stream errors (client gone), the writable errors,
    // which rejects the pipeTo promise, triggering the abort above.
    return new Response(readable, { headers: upstream.headers });
  },
};
```

---

## Anti-patterns

- **Reading the full body into memory before streaming**: `const buf = await upstream.arrayBuffer()` destroys all backpressure and memory bounds.
- **Unbounded `tee()`**: Teeing a stream clones chunks into both branches. If one branch is consumed slowly it buffers indefinitely. Use a bounded secondary cache strategy instead.
- **Ignoring `writer.ready`**: Writing in a tight `while` loop without awaiting `ready` fills the internal queue to the platform limit and may cause silent drops or CPU exhaustion.
- **Using `response.text()` on AI token streams**: Forces full buffering; use `response.body` directly.

---

## Gotchas

- `pipeTo` is fire-and-forget but errors in the pipe are swallowed unless you attach `.catch()`.
- Workers have a **6 MB** response body subrequest size limit in some contexts — streaming bypasses this for the response *to the client* but not for sub-fetches that are buffered.
- `ByteLengthQueuingStrategy` requires chunks to have a `.byteLength` property; plain strings will throw. Encode to `Uint8Array` first.
- Cloudflare does not implement `pipeThroughOptions.preventAbort`/`preventClose` on all paths — test abort behaviour explicitly.

---

## Verification

```typescript
// Instrument with a counting TransformStream to measure backpressure events.
let stallCount = 0;
const monitor = new TransformStream({
  async transform(chunk, controller) {
    if ((controller as any).desiredSize <= 0) stallCount++;
    controller.enqueue(chunk);
  },
});

// After the request: console.log('backpressure stalls:', stallCount);
```

Use `wrangler tail --format=pretty` and watch for CPU ms per request. If p99 CPU time drops
after adding backpressure, the previous implementation was burning CPU on queued writes.

---

## Related

- `workers-streaming-large-payloads.md`
- `workers-response-streaming-ttfb-optimization.md`
- `workers-streaming-response-tee-optimization.md`
- `workers-readable-stream-transform.md`
- `queues-consumer-backpressure-flow-control.md`

---

## Sources

- WHATWG Streams Standard — Backpressure and Internal Queues: https://streams.spec.whatwg.org/#backpressure
- Cloudflare Workers — Streams: https://developers.cloudflare.com/workers/runtime-apis/streams/
- Cloudflare Workers — Limits (CPU time): https://developers.cloudflare.com/workers/platform/limits/
