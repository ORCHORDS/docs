# Offloading CPU-Heavy Tasks to WASM Modules in Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker that runs CPU-intensive operations — image resizing, barcode parsing, cryptographic hashing, data compression, CSV/JSON transformation — saturates its CPU time budget (10–50 ms per request on the free tier, 30 s on paid). Compiling the hot loop to WebAssembly (WASM) from Rust or C typically yields 3–10× speedups over equivalent V8-optimized JavaScript, while staying within the same isolate with zero cold-start penalty.

## Context

- Runtime: Cloudflare Workers (V8 isolates with WASM support)
- Languages compiled to WASM: Rust (via `wasm-pack`), C/C++ (via Emscripten), Go (via TinyGo)
- Workers CPU limits: 10 ms (free), up to 30 s (paid Unbound)
- Memory: 128 MB per isolate (WASM linear memory counts toward this)
- Toolchain: `wasm-pack`, `wrangler`

---

## Section 1 — Compiling Rust to WASM for Workers

```bash
# Install toolchain
cargo install wasm-pack
rustup target add wasm32-unknown-unknown

# Scaffold a new Rust WASM library
cargo new --lib wasm-hasher
cd wasm-hasher
```

`Cargo.toml`:

```toml
[package]
name = "wasm-hasher"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]

[dependencies]
wasm-bindgen = "0.2"
sha2 = "0.10"
hex = "0.4"

[profile.release]
opt-level = 3
lto = true
codegen-units = 1
```

`src/lib.rs`:

```rust
use sha2::{Digest, Sha256};
use wasm_bindgen::prelude::*;

/// Returns the SHA-256 hex digest of the input bytes.
/// Exposed to JavaScript as `hashBytes(data: Uint8Array): string`.
#[wasm_bindgen]
pub fn hash_bytes(data: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hex::encode(hasher.finalize())
}

/// Parses a CSV-like payload and returns the sum of the second column.
/// Demonstrates numeric-heavy JS → WASM offload.
#[wasm_bindgen]
pub fn sum_column(csv: &str) -> f64 {
    csv.lines()
        .skip(1) // skip header
        .filter_map(|line| {
            let mut cols = line.splitn(3, ',');
            cols.nth(1)?.trim().parse::<f64>().ok()
        })
        .sum()
}
```

```bash
# Build optimised WASM + JS glue
wasm-pack build --target bundler --release
# Output: pkg/wasm_hasher_bg.wasm  + pkg/wasm_hasher.js
```

---

## Section 2 — Loading and Calling WASM from a Worker

`wrangler.toml`:

```toml
name = "wasm-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[rules]]
type = "CompiledWasm"
globs = ["**/*.wasm"]
fallthrough = true
```

`src/index.ts`:

```typescript
import wasmModule from '../wasm-hasher/pkg/wasm_hasher_bg.wasm';
import init, { hash_bytes, sum_column } from '../wasm-hasher/pkg/wasm_hasher';

export interface Env {}

// Initialise once per isolate — not per request.
// Workers reuse isolates across many requests, so this runs once on cold start.
let wasmInitialised = false;

async function ensureWasm(): Promise<void> {
  if (wasmInitialised) return;
  await init(wasmModule);
  wasmInitialised = true;
}

export default {
  async fetch(request: Request, _env: Env, _ctx: ExecutionContext): Promise<Response> {
    await ensureWasm();

    const url = new URL(request.url);
    const path = url.pathname;

    if (path === '/hash') {
      const body = await request.arrayBuffer();
      const data = new Uint8Array(body);

      const t0 = performance.now();
      const digest = hash_bytes(data);
      const elapsed = (performance.now() - t0).toFixed(3);

      return Response.json({ digest, elapsed_ms: elapsed });
    }

    if (path === '/sum') {
      const csv = await request.text();

      const t0 = performance.now();
      const total = sum_column(csv);
      const elapsed = (performance.now() - t0).toFixed(3);

      return Response.json({ total, elapsed_ms: elapsed });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

---

## Section 3 — Memory Limits and When WASM Beats JS

```typescript
// Memory budget check — Workers cap at 128 MB per isolate.
// WASM linear memory is allocated separately from the V8 heap.
// A 64 MB initial WASM heap leaves ~64 MB for V8.

// In Rust, control initial memory via wasm-bindgen or a custom allocator:
// #[global_allocator]
// static ALLOC: wee_alloc::WeeAlloc = wee_alloc::WeeAlloc::INIT;
// wee_alloc reduces WASM binary size and is more memory-conservative.

// Decision matrix: WASM vs JS
type ComputeProfile = {
  task: string;
  preferWasm: boolean;
  reason: string;
};

const COMPUTE_MATRIX: ComputeProfile[] = [
  { task: 'SHA-256 / SHA-512 hashing', preferWasm: true,  reason: 'WASM ~4× faster than SubtleCrypto for small payloads; no async overhead' },
  { task: 'Image resizing / pixel ops', preferWasm: true,  reason: 'SIMD-ready tight loops; JS GC pressure with large TypedArrays' },
  { task: 'CSV / binary parsing',      preferWasm: true,  reason: 'Zero-copy slice access; avoids JS string allocations' },
  { task: 'Regex matching',            preferWasm: false, reason: 'V8 regex engine is faster; WASM regex libs add binary bloat' },
  { task: 'JSON.parse',                preferWasm: false, reason: 'V8 built-in JSON.parse is native code; WASM serde adds overhead' },
  { task: 'Brotli / gzip compression', preferWasm: true,  reason: 'CompressionStream uses native WASM internally; direct WASM is faster for non-streaming' },
  { task: 'AES-GCM encryption',        preferWasm: false, reason: 'Use SubtleCrypto — hardware-accelerated on CF edge hardware' },
  { task: 'Base64 encode/decode',      preferWasm: false, reason: 'Workers provide atob/btoa; WASM overhead exceeds gain for <1 MB' },
];

// Log the matrix at startup for observability
console.log('Compute routing matrix:', JSON.stringify(COMPUTE_MATRIX, null, 2));

// WASM binary size budget: keep .wasm < 1 MB for fast isolate startup.
// Measure with:
// ls -lh wasm-hasher/pkg/wasm_hasher_bg.wasm
// wasm-opt -Oz -o optimized.wasm wasm_hasher_bg.wasm  (install binaryen)
```

---

## Anti-patterns

- Calling `init(wasmModule)` on every request — WASM compilation happens once per isolate; re-calling `init` is a no-op waste of time but signals misunderstanding
- Using WASM for tasks where `SubtleCrypto` or `CompressionStream` already uses hardware-accelerated native code
- Allocating large WASM linear memory (> 64 MB) — leaves too little headroom for V8 heap; causes OOM kills
- Importing WASM in a way that blocks module evaluation — always `await init(...)` inside the fetch handler on first call, not at module top level
- Shipping unoptimised WASM (`--dev` builds) — 3–5× slower than release builds and 2× larger

## Gotchas

- WASM modules imported via `[[rules]] type = "CompiledWasm"` are pre-compiled at deploy time, not at runtime — startup latency is near-zero
- Workers do NOT support WASM threads (`SharedArrayBuffer` + `Atomics`) — pure single-threaded WASM only
- WASM linear memory cannot be grown beyond the `maximum` set at compile time; Rust's default is unbounded but Workers will OOM at 128 MB
- `wasm-pack build --target bundler` produces ESM glue compatible with Wrangler's bundler; `--target web` does not work in Workers
- WASM binary size counts toward the 1 MB (free) / 10 MB (paid) Worker script size limit

## Verification

```bash
# Build and check binary size
wasm-pack build --target bundler --release
ls -lh wasm-hasher/pkg/wasm_hasher_bg.wasm

# Optional: optimise with binaryen
npm install -g binaryen
wasm-opt -Oz \
  wasm-hasher/pkg/wasm_hasher_bg.wasm \
  -o wasm-hasher/pkg/wasm_hasher_bg.wasm
ls -lh wasm-hasher/pkg/wasm_hasher_bg.wasm

# Deploy
wrangler deploy

# Smoke test hash endpoint
echo -n 'hello world' | \
  curl -s -X POST \
    -H 'Content-Type: application/octet-stream' \
    --data-binary @- \
    https://your-worker.workers.dev/hash
# Expected: {"digest":"b94d27b9934d3e08a52e52d7da7dabfac484efe04294e576b7b5b29c92b63d35", ...}
# (SHA-256 of 'hello world')

# Benchmark: compare WASM hash vs SubtleCrypto via wrangler dev
wrangler dev --local false
```

## Related

- `documentation/docs/policies/performance/workers-brotli-compression-response-optimization.md`
- `documentation/docs/policies/performance/workers-d1-index-covering-query-optimization.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://developers.cloudflare.com/workers/wrangler/configuration/#bundling
- https://rustwasm.github.io/wasm-pack/book/
- https://developers.cloudflare.com/workers/platform/limits/#memory
