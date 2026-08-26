# WebAssembly SIMD Performance in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Workers endpoint that performs CPU-heavy operations — image thumbnail generation, audio waveform extraction, JSON schema validation over large payloads, or cryptographic hashing — is hitting the 50 ms CPU-time limit or returning high p99 latencies. Profiling shows the bottleneck is a tight inner loop operating on byte arrays or numeric buffers. Switching the computation to a Wasm module compiled with SIMD 128-bit vector instructions can reduce runtime by 2–8× for data-parallel workloads.

## Context

V8 (the JavaScript engine in Cloudflare Workers) supports the WebAssembly Fixed-Width SIMD proposal (`wasm32-unknown-unknown` target with `-msimd128`). SIMD allows a single instruction to operate on 16 bytes simultaneously using 128-bit XMM-equivalent registers — the same concept as SSE2/NEON but portable across x86-64 and ARM64 edge nodes. Workers runs on both architectures; the V8 engine JITs Wasm SIMD intrinsics to native vector instructions automatically. The key constraint is that V8 validates and compiles the Wasm module during Worker startup: streaming compilation (instantiating from a `Response`) is not available inside Workers, so use static `import` of the `.wasm` file via Wrangler's `[[wasm_modules]]` binding.

## Compiling a SIMD Wasm Module

```bash
# Rust toolchain — most ergonomic for Workers Wasm
cargo install wasm-pack

# Compile with SIMD128 target feature enabled
RUSTFLAGS="-C target-feature=+simd128" \
  wasm-pack build --target bundler --out-dir pkg

# Or from C/C++ with Emscripten
emcc -O3 -msimd128 -msse4.1 src/hash.c -o hash.wasm \
  -s STANDALONE_WASM=1 -s EXPORTED_FUNCTIONS="['_process_block']"
```

```toml
# wrangler.toml — bind the compiled Wasm module
name = "simd-worker"
compatibility_date = "2026-08-01"

[[wasm_modules]]
name = "HASH_WASM"
path = "pkg/simd_worker_bg.wasm"
```

## Instantiating and Calling the Wasm Module

```typescript
// The Wasm module is available as a global WebAssembly.Module via the binding name
declare const HASH_WASM: WebAssembly.Module;

interface Env {
  HASH_WASM: WebAssembly.Module;
}

// Cache the instance across requests in the same isolate to avoid
// repeated instantiation cost (~0.5–2 ms per cold call)
let wasmInstance: WebAssembly.Instance | null = null;

function getWasmInstance(module: WebAssembly.Module): WebAssembly.Instance {
  if (wasmInstance) return wasmInstance;
  wasmInstance = new WebAssembly.Instance(module, {
    env: {
      // Provide any imports the Wasm module needs (e.g. abort handler for Rust)
      abort: (msg: number, file: number, line: number, col: number) => {
        throw new Error(`Wasm abort: ${msg} at ${file}:${line}:${col}`);
      },
    },
  });
  return wasmInstance;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("POST a binary body", { status: 405 });
    }

    const body = await request.arrayBuffer();
    const instance = getWasmInstance(env.HASH_WASM);
    const exports = instance.exports as {
      process_block: (ptr: number, len: number) => number;
      memory: WebAssembly.Memory;
      alloc: (size: number) => number;
      free: (ptr: number, size: number) => void;
    };

    const inputBytes = new Uint8Array(body);
    const len = inputBytes.byteLength;

    // Allocate Wasm memory, copy input, call SIMD function, read result
    const ptr = exports.alloc(len);
    try {
      const mem = new Uint8Array(exports.memory.buffer, ptr, len);
      mem.set(inputBytes);

      const resultCode = exports.process_block(ptr, len);
      return new Response(JSON.stringify({ result: resultCode, bytes: len }), {
        headers: { "Content-Type": "application/json" },
      });
    } finally {
      exports.free(ptr, len);
    }
  },
};
```

## SIMD-Accelerated Image Grayscale Conversion Example

```typescript
// Rust source snippet (compiled with wasm-pack + simd128 feature)
// This is the Wasm counterpart to the TypeScript caller above

/*
use std::arch::wasm32::*;  // wasm32 SIMD intrinsics

#[no_mangle]
pub unsafe extern "C" fn rgba_to_grayscale(ptr: *mut u8, pixel_count: usize) {
    // Weights: R=0.299, G=0.587, B=0.114 as fixed-point (shift 8)
    let wr = i16x8_splat(77);   // 0.299 * 256
    let wg = i16x8_splat(150);  // 0.587 * 256
    let wb = i16x8_splat(29);   // 0.114 * 256

    let mut i = 0usize;
    // Process 4 RGBA pixels = 16 bytes per SIMD lane
    while i + 16 <= pixel_count * 4 {
        let chunk = v128_load(ptr.add(i) as *const v128);
        // Shuffle to extract R, G, B channels into separate lanes
        // ... (see full source in /wasm/src/lib.rs)
        i += 16;
    }
    // Scalar tail for remaining pixels
}
*/

// TypeScript caller
async function processImage(env: Env, imageData: ArrayBuffer): Promise<ArrayBuffer> {
  const instance = getWasmInstance(env.HASH_WASM);
  const { rgba_to_grayscale, memory, alloc, free } = instance.exports as {
    rgba_to_grayscale: (ptr: number, pixelCount: number) => void;
    memory: WebAssembly.Memory;
    alloc: (n: number) => number;
    free: (ptr: number, n: number) => void;
  };

  const input = new Uint8Array(imageData);
  const pixelCount = input.byteLength / 4;
  const ptr = alloc(input.byteLength);
  new Uint8Array(memory.buffer, ptr, input.byteLength).set(input);
  rgba_to_grayscale(ptr, pixelCount);
  const result = new Uint8Array(memory.buffer, ptr, input.byteLength).slice();
  free(ptr, input.byteLength);
  return result.buffer;
}
```

## Benchmarking SIMD vs Scalar

```typescript
// Simple in-Worker microbenchmark — run with `wrangler dev`
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const size = 1024 * 1024; // 1 MB
    const data = crypto.getRandomValues(new Uint8Array(size));

    // Scalar baseline (pure JS)
    const t0 = performance.now();
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i];
    const jsTime = performance.now() - t0;

    // SIMD Wasm path
    const t1 = performance.now();
    const instance = getWasmInstance(env.HASH_WASM);
    const { sum_bytes, memory, alloc, free } = instance.exports as any;
    const ptr = alloc(size);
    new Uint8Array(memory.buffer, ptr, size).set(data);
    const wasmSum = sum_bytes(ptr, size);
    free(ptr, size);
    const wasmTime = performance.now() - t1;

    return Response.json({
      jsTime: `${jsTime.toFixed(2)}ms`,
      wasmSimdTime: `${wasmTime.toFixed(2)}ms`,
      speedup: `${(jsTime / wasmTime).toFixed(1)}x`,
    });
  },
};
```

## Anti-patterns

- Instantiating `new WebAssembly.Instance(module)` inside the `fetch` handler on every request — pay the compile/instantiation cost once per isolate by caching the instance in module scope.
- Using `WebAssembly.instantiateStreaming()` — this API is not available in the Workers runtime; use the `[[wasm_modules]]` binding which provides a pre-compiled `WebAssembly.Module`.
- Allocating large Wasm memory for small inputs — the Wasm linear memory grows but never shrinks; size `alloc` calls to the actual input size and free promptly.

## Gotchas

- Workers has a 128 MB memory limit per isolate; Wasm linear memory counts toward this budget. A Wasm module with `(memory 64)` (64 pages = 4 MB) reserves that at instantiation time.
- SIMD128 opcodes are always valid in the Workers V8 build — you do not need a feature-detection branch; all edge nodes support them.

## Verification

```bash
# Check that the compiled Wasm binary contains SIMD opcodes
wasm-objdump -d pkg/simd_worker_bg.wasm | grep -c "v128\|i8x16\|i16x8\|f32x4"

# Deploy and benchmark via wrk
wrangler deploy
wrk -t4 -c50 -d10s --script post-binary.lua https://simd-worker.example.workers.dev/process

# Confirm CPU-time savings in Cloudflare dashboard
# Analytics > Workers > CPU Time — compare p99 before/after SIMD migration
```

## Related

- `performance/webassembly-streaming-compilation-delivery-contract.md`
- `performance/workers-cpu-time-optimization.md`
- `performance/workers-cpu-profiling.md`
- `performance/workers-memory-allocation-optimization.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://github.com/WebAssembly/simd/blob/master/proposals/simd/SIMD.md
- https://rustwasm.github.io/wasm-pack/book/
- https://v8.dev/features/simd
