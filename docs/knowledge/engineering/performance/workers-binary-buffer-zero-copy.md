# Workers Binary Buffer Zero-Copy Performance

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker processes binary payloads — image transforms, Wasm invocations, R2 reads, WebSocket
frames — and CPU time is unexpectedly high relative to payload size. Profiling reveals time spent
in memory allocations and buffer copies rather than actual computation. Replacing `ArrayBuffer`
copies with shared-view patterns (zero-copy) can halve CPU time on 1–16 MB payloads.

---

## Context

Workers run inside V8 isolates with a 128 MB heap limit. Every `new Uint8Array(src)`,
`Buffer.from(src)`, or `slice()` that allocates a new backing store is a copy. The WHATWG
`TypedArray` spec distinguishes between operations that share the underlying `ArrayBuffer`
(zero-copy views) and those that allocate a new one. Understanding this distinction is the key
to writing high-throughput binary Workers.

Zero-copy rules of thumb:
- `new Uint8Array(existingArrayBuffer)` → **shared view** (zero-copy)
- `new Uint8Array(existingArrayBuffer).slice()` → **new allocation** (copy)
- `new Uint8Array(existingArrayBuffer).subarray()` → **shared view** (zero-copy)
- `TypedArray.set(other)` → in-place copy into an existing buffer (one copy, no extra alloc)

---

## Shared Views with `subarray`

Use `subarray` instead of `slice` when you need a window into a buffer without copying.

```typescript
export default {
  async fetch(request: Request): Promise<Response> {
    const body = await request.arrayBuffer();
    const view = new Uint8Array(body);

    // Zero-copy: both share the same ArrayBuffer backing store.
    const header = view.subarray(0, 16);   // first 16 bytes — no alloc
    const payload = view.subarray(16);     // rest — no alloc

    const magic = new DataView(header.buffer, header.byteOffset, header.byteLength);
    if (magic.getUint32(0, false) !== 0xdeadbeef) {
      return new Response('bad magic', { status: 400 });
    }

    return new Response(payload); // pass the view directly — no extra copy
  },
};
```

---

## Pre-allocated Output Buffers with `TypedArray.set`

When assembling a response from multiple input segments, pre-allocate a single output buffer and
fill it with `set()` rather than concatenating with spread or `Buffer.concat`.

```typescript
function assembleFrames(frames: Uint8Array[]): Uint8Array {
  const totalLength = frames.reduce((n, f) => n + f.byteLength, 0);
  const out = new Uint8Array(totalLength); // one allocation
  let offset = 0;
  for (const frame of frames) {
    out.set(frame, offset); // in-place copy — no intermediate allocations
    offset += frame.byteLength;
  }
  return out;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const object = await env.R2.get('chunks/manifest.bin');
    const manifest = new Uint8Array(await object!.arrayBuffer());

    // Parse chunk offsets from manifest and fetch in parallel (see r2-multipart files).
    const chunkIds = parseManifest(manifest);
    const chunks = await Promise.all(chunkIds.map((id) => fetchChunk(env, id)));

    return new Response(assembleFrames(chunks), {
      headers: { 'Content-Type': 'application/octet-stream' },
    });
  },
};
```

---

## DataView for Structured Parsing Without Extra Copies

`DataView` can read multi-byte values directly from an `ArrayBuffer` at any byte offset without
creating intermediate typed arrays or string conversions.

```typescript
function parseHeader(buf: ArrayBuffer): { version: number; payloadLength: number } {
  const dv = new DataView(buf);
  return {
    version: dv.getUint8(0),
    payloadLength: dv.getUint32(1, /* littleEndian */ true),
  };
}

export default {
  async fetch(request: Request): Promise<Response> {
    const raw = await request.arrayBuffer();
    const { version, payloadLength } = parseHeader(raw);

    if (version !== 2) return new Response('unsupported version', { status: 415 });

    // subarray the payload region — zero extra allocation
    const payload = new Uint8Array(raw, 5, payloadLength);
    const result = processPayload(payload);

    return new Response(result.buffer, { headers: { 'Content-Type': 'application/octet-stream' } });
  },
};
```

`new Uint8Array(buffer, byteOffset, length)` is the three-argument constructor that creates an
offset view — another zero-copy path.

---

## Streaming Zero-Copy with `TransformStream`

For large bodies, avoid buffering the full `ArrayBuffer` at all. Transform chunks in-place by
operating on the `Uint8Array` view the stream hands you.

```typescript
function xorTransform(key: number): TransformStream<Uint8Array, Uint8Array> {
  return new TransformStream({
    transform(chunk, controller) {
      // Mutate in-place — no new allocation.
      for (let i = 0; i < chunk.byteLength; i++) {
        chunk[i] ^= key;
      }
      controller.enqueue(chunk); // same reference, zero extra copy
    },
  });
}

export default {
  async fetch(request: Request): Promise<Response> {
    const { readable, writable } = xorTransform(0x42);
    request.body!.pipeTo(writable);
    return new Response(readable);
  },
};
```

Mutating the chunk in-place is safe here because the stream runtime does not retain the chunk
after `transform` returns.

---

## Anti-patterns

- **`Array.from(uint8Array)`**: Converts binary data to a JS number array — 8× memory, GC pressure.
- **String concatenation for binary**: `chunk.toString('hex')` or `atob/btoa` round-trips allocate new strings; use `TextDecoder` only for actual text content.
- **`new Uint8Array([...existing])`**: Spread operator forces a full copy into a new array before the TypedArray constructor runs.
- **`Buffer.concat(buffers)`**: Available in Workers via the compatibility flag but still allocates a new backing store; prefer `TypedArray.set` with a pre-sized output.
- **`slice()` in hot paths**: Easy to write, always allocates. Audit with `--cpuTimeLimit` profiling.

---

## Gotchas

- Mutating a chunk in a `transform()` callback is safe, but mutating a chunk after `enqueue()` is not — the runtime may alias the buffer.
- `new DataView(typedArray.buffer, typedArray.byteOffset, typedArray.byteLength)` is required when the TypedArray is itself an offset view (not at position 0 of its buffer); omitting the offset/length reads wrong bytes.
- Workers' `Response` constructor accepts `ArrayBuffer`, `ArrayBufferView`, `ReadableStream`, or `string` — passing a `Uint8Array` subarray works because `Uint8Array` implements `ArrayBufferView`.
- The V8 heap limit (128 MB) counts *all live* ArrayBuffers; large zero-copy views still count toward the limit because they keep their backing `ArrayBuffer` alive.

---

## Verification

```bash
# Measure CPU time before and after zero-copy refactor using wrangler dev:
wrangler dev --inspector-port 9229

# In Chrome DevTools → Profiler → record a heap snapshot.
# Compare "(array buffer)" memory between implementations.

# Alternatively, use the Workers CPU time metric in the dashboard:
# Workers & Pages → [worker] → Metrics → CPU Time (p50/p99)
```

A successful zero-copy refactor on 4 MB payloads typically reduces p99 CPU time by 30–60% and
eliminates GC pause spikes visible in the heap timeline.

---

## Related

- `workers-memory-allocation-optimization.md`
- `workers-wasm-module-caching.md`
- `r2-multipart-download-parallel-chunk-assembly.md`
- `workers-readable-stream-transform.md`
- `webassembly-simd-workers-performance.md`

---

## Sources

- MDN — TypedArray `subarray` vs `slice`: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/TypedArray/subarray
- MDN — DataView: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/DataView
- Cloudflare Workers — Memory limits: https://developers.cloudflare.com/workers/platform/limits/#memory
- V8 Blog — Zero-copy ArrayBuffer transfer: https://v8.dev/blog/arraybuffer-transfer
