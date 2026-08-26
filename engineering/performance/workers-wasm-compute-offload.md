# WebAssembly Compute Offload in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Worker performs CPU-intensive tasks — hashing large payloads, encoding audio
metadata, running image transforms, or computing complex search rankings — in
pure JavaScript. CPU time exceeds the Workers limit (10 ms on free, 30 s on
paid) or the operation is too slow for inline use.

Common signals:
- `CPU time limit exceeded` errors in Wrangler tail logs.
- Operation takes > 5 ms per request in JS (noticeable at p99 under load).
- Profiling shows > 80 % of CPU time in a tight computational loop.

---

## Context

Cloudflare Workers support WebAssembly (WASM) as a first-class module type.
WASM binaries run in the same V8 isolate as the JavaScript Worker, sharing
memory and the same CPU-time budget. However, WASM code compiled from Rust or
C typically outperforms equivalent JavaScript by 2–10× for compute-bound
workloads (hash, compression, encoding, parsing) because:

- WASM operates on typed memory without GC pauses.
- V8's WASM JIT (TurboFan) emits tighter machine code than JS for numeric loops.
- SIMD instructions (via `wasm-simd`) can be used in Workers.

The workflow is: compile a Rust (or C) library to WASM, bundle the `.wasm`
binary as a module-scope import, instantiate it once at startup, and call
exported functions from TypeScript.

---

## Solution

```typescript
// wasm-worker.ts
// Demonstrates three WASM use-cases:
//   1. xxHash64 — fast non-cryptographic hash (Rust → WASM)
//   2. DEFLATE compression — zlib-rs (Rust) for finer level control
//   3. Benchmarking harness — JS vs WASM for the same operation

import type { ExecutionContext } from '@cloudflare/workers-types';

// ---------------------------------------------------------------------------
// WASM module imports
// In wrangler.toml:
//   [[wasm_modules]]
//   name = "XXHASH_WASM"
//   path = "wasm/xxhash.wasm"
//
//   [[wasm_modules]]
//   name = "DEFLATE_WASM"
//   path = "wasm/deflate.wasm"
//
// The runtime injects these as WebAssembly.Module values.
// ---------------------------------------------------------------------------

declare const XXHASH_WASM: WebAssembly.Module;
declare const DEFLATE_WASM: WebAssembly.Module;

export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

// ---------------------------------------------------------------------------
// Module-scope WASM instances
// Instantiated once when the isolate cold-starts, reused across all requests.
// This avoids paying WebAssembly.instantiate() cost on every request.
// ---------------------------------------------------------------------------

interface XxHashExports {
  memory: WebAssembly.Memory;
  alloc: (size: number) => number;  // malloc equivalent
  dealloc: (ptr: number, size: number) => void;
  xxhash64: (ptr: number, len: number, seed: bigint) => bigint;
}

interface DeflateExports {
  memory: WebAssembly.Memory;
  alloc: (size: number) => number;
  dealloc: (ptr: number, size: number) => void;
  compress: (inPtr: number, inLen: number, outPtr: number, level: number) => number;
  max_output_size: (inputLen: number) => number;
}

// Lazy singleton pattern: instantiate on first use, cache the exports.
let xxhashExports: XxHashExports | null = null;
let deflateExports: DeflateExports | null = null;

async function getXxHash(): Promise<XxHashExports> {
  if (!xxhashExports) {
    const instance = await WebAssembly.instantiate(XXHASH_WASM, {});
    xxhashExports = instance.exports as unknown as XxHashExports;
  }
  return xxhashExports;
}

async function getDeflate(): Promise<DeflateExports> {
  if (!deflateExports) {
    const instance = await WebAssembly.instantiate(DEFLATE_WASM, {});
    deflateExports = instance.exports as unknown as DeflateExports;
  }
  return deflateExports;
}

// ---------------------------------------------------------------------------
// xxHash64 wrapper
// Copies input bytes into WASM linear memory, calls the export, copies result.
// ---------------------------------------------------------------------------

async function xxhash64(input: Uint8Array, seed = 0n): Promise<bigint> {
  const wasm = await getXxHash();

  const ptr = wasm.alloc(input.byteLength);
  try {
    const mem = new Uint8Array(wasm.memory.buffer);
    mem.set(input, ptr);
    return wasm.xxhash64(ptr, input.byteLength, seed);
  } finally {
    wasm.dealloc(ptr, input.byteLength);
  }
}

// ---------------------------------------------------------------------------
// DEFLATE compression wrapper
// Allows specifying compression level (1–9), unlike CompressionStream.
// ---------------------------------------------------------------------------

async function deflateCompress(
  input: Uint8Array,
  level: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 = 6
): Promise<Uint8Array> {
  const wasm = await getDeflate();

  const maxOut = wasm.max_output_size(input.byteLength);
  const inPtr = wasm.alloc(input.byteLength);
  const outPtr = wasm.alloc(maxOut);

  try {
    const mem = new Uint8Array(wasm.memory.buffer);
    mem.set(input, inPtr);

    const compressedLen = wasm.compress(inPtr, input.byteLength, outPtr, level);
    if (compressedLen < 0) {
      throw new Error(`WASM deflate failed: error code ${compressedLen}`);
    }

    // Copy result out before dealloc
    return new Uint8Array(wasm.memory.buffer, outPtr, compressedLen).slice();
  } finally {
    wasm.dealloc(inPtr, input.byteLength);
    wasm.dealloc(outPtr, maxOut);
  }
}

// ---------------------------------------------------------------------------
// Benchmarking harness — JS vs WASM
// Returns timing and output for both implementations.
// ---------------------------------------------------------------------------

const encoder = new TextEncoder();

async function benchmarkHash(payload: string): Promise<{
  jsDurationMs: number;
  wasmDurationMs: number;
  jsResult: string;
  wasmResult: string;
  speedupX: number;
}> {
  const bytes = encoder.encode(payload);

  // JS implementation: SubtleCrypto SHA-1 (fast, not cryptographic quality
  // but comparable in CPU expense to xxHash64 at small sizes)
  const jsStart = performance.now();
  const jsHash = await crypto.subtle.digest('SHA-1', bytes);
  const jsDurationMs = performance.now() - jsStart;
  const jsResult = Array.from(new Uint8Array(jsHash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');

  // WASM xxHash64
  const wasmStart = performance.now();
  const wasmHash = await xxhash64(bytes);
  const wasmDurationMs = performance.now() - wasmStart;
  const wasmResult = wasmHash.toString(16);

  return {
    jsDurationMs,
    wasmDurationMs,
    jsResult,
    wasmResult,
    speedupX: jsDurationMs / wasmDurationMs,
  };
}

// ---------------------------------------------------------------------------
// Request handler
// Routes:
//   GET /hash?payload=<text>       — xxHash64 of payload
//   GET /compress?payload=<text>   — DEFLATE compress payload, return hex
//   GET /benchmark?payload=<text>  — compare JS vs WASM hash
// ---------------------------------------------------------------------------

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const payload = url.searchParams.get('payload') ?? 'hello orchords';

    try {
      if (url.pathname === '/hash') {
        const bytes = encoder.encode(payload);
        const start = performance.now();
        const hash = await xxhash64(bytes);
        const durationMs = performance.now() - start;

        ctx.waitUntil(
          recordWasmMetric(env.ANALYTICS, 'hash', bytes.byteLength, durationMs)
        );

        return new Response(
          JSON.stringify({ hash: hash.toString(16), durationMs }),
          { headers: { 'content-type': 'application/json' } }
        );
      }

      if (url.pathname === '/compress') {
        const levelParam = parseInt(url.searchParams.get('level') ?? '6', 10);
        const level = Math.min(9, Math.max(1, levelParam)) as 1|2|3|4|5|6|7|8|9;
        const bytes = encoder.encode(payload);
        const start = performance.now();
        const compressed = await deflateCompress(bytes, level);
        const durationMs = performance.now() - start;
        const ratio = compressed.byteLength / bytes.byteLength;

        ctx.waitUntil(
          recordWasmMetric(env.ANALYTICS, 'compress', bytes.byteLength, durationMs)
        );

        const hex = Array.from(compressed)
          .map((b) => b.toString(16).padStart(2, '0'))
          .join('');

        return new Response(
          JSON.stringify({
            originalBytes: bytes.byteLength,
            compressedBytes: compressed.byteLength,
            ratio: ratio.toFixed(3),
            level,
            durationMs,
            hex,
          }),
          { headers: { 'content-type': 'application/json' } }
        );
      }

      if (url.pathname === '/benchmark') {
        const result = await benchmarkHash(payload);
        return new Response(JSON.stringify(result, null, 2), {
          headers: { 'content-type': 'application/json' },
        });
      }

      return new Response('Not found', { status: 404 });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return new Response(JSON.stringify({ error: msg }), {
        status: 500,
        headers: { 'content-type': 'application/json' },
      });
    }
  },
};

// ---------------------------------------------------------------------------
// Analytics Engine helper
// ---------------------------------------------------------------------------

async function recordWasmMetric(
  dataset: AnalyticsEngineDataset,
  operation: string,
  inputBytes: number,
  durationMs: number
): Promise<void> {
  try {
    dataset.writeDataPoint({
      blobs: [operation],
      doubles: [inputBytes, durationMs],
      indexes: [operation],
    });
  } catch {
    // Non-critical
  }
}
```

---

## Implementation Details

**Module-scope instantiation**: `WebAssembly.instantiate()` is called once per
isolate warm-start and the `exports` object is cached. Subsequent requests
reuse the same WASM instance — including its linear memory — without paying
the startup cost again.

**Memory management**: WASM modules compiled from Rust expose `alloc`/`dealloc`
(backed by `wee_alloc` or the default allocator). Always `dealloc` in a
`finally` block to prevent memory leaks across requests sharing the isolate.

**WASM size optimisation** (Rust build flags in `Cargo.toml`):
```toml
[profile.release]
opt-level = "s"      # optimise for size
lto = true
codegen-units = 1
panic = "abort"      # removes panic infrastructure
strip = true
```
Target `wasm32-unknown-unknown` and pass `--no-default-features` to strip
transitive dependencies. Run `wasm-opt -Os` (from `binaryen`) as a post-compile
step to reduce binary size by a further 10–30 %.

**SIMD**: Add `target-feature = "+simd128"` in `.cargo/config.toml` for
algorithms that benefit from 128-bit SIMD (AES, SHA, certain hash functions).
Workers runtime supports `wasm-simd`.

**Benchmark interpretation**: For payloads under ~1 KB, JS `SubtleCrypto` may
outperform WASM due to its native C implementation. WASM wins at larger payloads
where the JS JIT overhead is amortised and tight loops dominate.

---

## Anti-patterns

- **Instantiating WASM per request**: `WebAssembly.instantiate()` inside the
  `fetch` handler pays the compilation cost on every request. Use module-scope
  lazy singletons.
- **Forgetting `dealloc`**: WASM linear memory does not have a GC. Failing to
  free allocations causes unbounded memory growth and eventual OOM kills of the
  isolate.
- **Using WASM for I/O-bound work**: WASM offers no advantage for fetch, KV, or
  D1 calls — those are async I/O, not CPU. Use WASM only for compute-bound work.
- **Shipping debug WASM builds**: A debug WASM binary can be 10× larger than a
  release build and 5× slower. Always use `--release` + `wasm-opt`.

---

## Gotchas

- WASM linear memory (`wasm.memory.buffer`) is an `ArrayBuffer` that can be
  detached if the WASM module grows its memory. Always construct the `Uint8Array`
  view **after** calling the WASM function that may grow memory, and re-fetch
  `wasm.memory.buffer` if you see `detached ArrayBuffer` errors.
- `WebAssembly.Module` (declared in `wrangler.toml`) is injected as a global by
  the Workers runtime. In local development (`wrangler dev`), you may need to
  pass `--local` and ensure the `.wasm` file path is correct.
- The Workers CPU time limit includes WASM execution time. WASM is faster but
  not free; very large inputs can still exceed limits.
- `bigint` return types from WASM exports require `--target es2020` or later in
  `tsconfig.json` (`"lib": ["ES2020"]`).

---

## Verification

```bash
# Build Rust to WASM (requires wasm-pack or cargo)
cargo build --release --target wasm32-unknown-unknown
wasm-opt -Os target/wasm32-unknown-unknown/release/xxhash.wasm -o wasm/xxhash.wasm

# Check WASM binary size
ls -lh wasm/xxhash.wasm
# Aim for < 50 KB for a single-purpose utility module

# Deploy and test
wrangler deploy
curl 'https://wasm.example.com/benchmark?payload=hello+world'
# speedupX > 2 for payloads > 10 KB indicates WASM is worthwhile

# Confirm WASM is loaded at module scope (not per-request)
# Check Wrangler tail — startup log should show instantiation only once per isolate
wrangler tail --format json | jq '.logs[] | select(.message | contains("wasm"))'
```

---

## Related

- `workers-response-compression-brotli.md` — WASM brotli encoder for compression
- `workers-ttfb-optimization.md` — CPU-time budget considerations for streaming responses
- `workers-connection-coalescing.md` — Parallel fetch patterns for non-CPU bottlenecks

---

## Sources

- [Cloudflare Workers — WASM modules](https://developers.cloudflare.com/workers/wrangler/configuration/#webassembly-modules)
- [wasm-bindgen — Rust WASM toolchain](https://rustwasm.github.io/wasm-bindgen/)
- [wasm-opt — binaryen optimiser](https://github.com/WebAssembly/binaryen)
- [WebAssembly.instantiate — MDN](https://developer.mozilla.org/en-US/docs/WebAssembly/JavaScript_interface/instantiate_static)
- [Cloudflare Workers CPU limits](https://developers.cloudflare.com/workers/platform/limits/#cpu-time)
