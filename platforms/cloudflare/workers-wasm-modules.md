# WebAssembly Modules in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to run CPU-intensive logic at the edge — image processing, cryptographic hashing, compression, or custom parsers — but JavaScript is too slow and you can't reach an external service from within a Worker's CPU budget. You want to ship a compiled Rust, C, or AssemblyScript binary as a `.wasm` module and call it directly from Workers TypeScript.

## Context

Cloudflare Workers supports WebAssembly via the standard `WebAssembly` global. Wasm modules are imported like ES module assets in the `module` Worker format. The runtime instantiates the module per isolate (not per request), so the compiled code is warm after the first request. Workers' 128 MB memory limit applies to the combined JS + Wasm heap. Cold-start cost for a small Wasm binary (< 500 KB) is typically < 5 ms.

Wasm cannot make network calls or access Workers bindings directly — it must call back into JS for I/O. Keep Wasm for pure computation; orchestrate I/O in TypeScript.

---

## 1. Project Layout with wasm-pack (Rust)

```
my-worker/
  src/
    lib.rs          # Rust logic
  pkg/              # wasm-pack output — do not commit
  worker/
    src/
      index.ts
  wrangler.toml
```

`wrangler.toml`:
```toml
name = "wasm-worker"
main = "worker/src/index.ts"
compatibility_date = "2025-09-01"

[[rules]]
type = "CompiledWasm"
globs = ["**/*.wasm"]
fallthrough = true
```

---

## 2. Rust Source and Build

`src/lib.rs`:
```rust
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub fn hash_djb2(input: &str) -> u32 {
    input.bytes().fold(5381u32, |acc, b| {
        acc.wrapping_mul(33).wrapping_add(b as u32)
    })
}

#[wasm_bindgen]
pub fn compress_rle(data: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(data.len());
    let mut i = 0;
    while i < data.len() {
        let byte = data[i];
        let mut count = 1u8;
        while i + count as usize < data.len()
            && data[i + count as usize] == byte
            && count < 255
        {
            count += 1;
        }
        out.push(count);
        out.push(byte);
        i += count as usize;
    }
    out
}
```

Build:
```bash
wasm-pack build --target bundler --out-dir worker/pkg
```

---

## 3. Importing and Instantiating in TypeScript

```typescript
// worker/src/index.ts
import init, { hash_djb2, compress_rle } from "../pkg/my_worker";
import wasmUrl from "../pkg/my_worker_bg.wasm";

// Module-scope: instantiate once per isolate
let wasmReady: Promise<void> | null = null;

function ensureWasm(): Promise<void> {
  if (!wasmReady) {
    wasmReady = init(wasmUrl);
  }
  return wasmReady;
}

export default {
  async fetch(request: Request): Promise<Response> {
    await ensureWasm();

    const body = await request.arrayBuffer();
    const bytes = new Uint8Array(body);

    const hash = hash_djb2(new TextDecoder().decode(bytes));
    const compressed = compress_rle(bytes);

    return Response.json({
      originalBytes: bytes.length,
      compressedBytes: compressed.length,
      ratio: (compressed.length / bytes.length).toFixed(3),
      hash: hash.toString(16),
    });
  },
} satisfies ExportedHandler;
```

---

## 4. Passing Data Between JS and Wasm Efficiently

Avoid repeated `TextEncoder`/`TextDecoder` round-trips in hot paths. Use Wasm memory directly when the binary is large:

```typescript
import { WasmProcessor } from "../pkg/my_worker";

export default {
  async fetch(request: Request): Promise<Response> {
    await ensureWasm();

    const buffer = await request.arrayBuffer();
    const input = new Uint8Array(buffer);

    // Allocate in Wasm memory — avoids a JS-side copy
    const processor = new WasmProcessor();
    processor.load(input);
    const result = processor.process(); // returns Uint8Array view into wasm heap
    const output = result.slice();      // copy out before processor is freed
    processor.free();

    return new Response(output, {
      headers: { "Content-Type": "application/octet-stream" },
    });
  },
} satisfies ExportedHandler;
```

---

## 5. AssemblyScript Alternative (No Build Toolchain)

For simpler cases, AssemblyScript compiles TypeScript-like syntax to Wasm without Rust:

```typescript
// assembly/index.ts (AssemblyScript)
export function fibonacci(n: i32): i32 {
  if (n <= 1) return n;
  let a = 0, b = 1;
  for (let i = 2; i <= n; i++) {
    const tmp = a + b;
    a = b;
    b = tmp;
  }
  return b;
}
```

```bash
npx asc assembly/index.ts --outFile worker/fib.wasm --optimize
```

```typescript
// worker/src/index.ts
import wasmModule from "./fib.wasm";

const { instance } = await WebAssembly.instantiate(wasmModule, {});
const { fibonacci } = instance.exports as { fibonacci: (n: number) => number };

export default {
  async fetch(req: Request): Promise<Response> {
    const n = parseInt(new URL(req.url).searchParams.get("n") ?? "10");
    return Response.json({ result: fibonacci(Math.min(n, 80)) });
  },
} satisfies ExportedHandler;
```

---

## Anti-patterns

- **Instantiating per request** — `WebAssembly.instantiate()` inside the `fetch` handler re-parses the binary on every request. Hoist to module scope or use a lazy singleton.
- **Blocking network I/O from Wasm** — Wasm cannot call `fetch()` or use Workers bindings. Keep I/O in JS; pass results into Wasm functions.
- **Unbounded heap growth** — Wasm memory only grows, never shrinks within an isolate. Cache the `WasmProcessor` instance rather than allocating a new one per request if the Worker handles large payloads at high concurrency.
- **Shipping debug builds** — `wasm-pack build` without `--release` produces 10× larger binaries. Always use `--release` for production.

---

## Gotchas

- The `CompiledWasm` rule in `wrangler.toml` is required for `.wasm` files; without it Wrangler treats them as static assets and upload fails.
- `wasm-bindgen` generated glue imports from `./my_worker_bg.wasm` using a relative path — if you restructure `pkg/`, fix the import alias in `tsconfig.json` paths or the Wrangler `[[rules]]` glob.
- Workers enforces a 1 MB compressed script size limit per bundle. A Rust binary with full `std` can exceed this — use `#![no_std]` with `wee_alloc` or switch to AssemblyScript for size-sensitive functions.
- `WebAssembly.instantiateStreaming()` is NOT supported in Workers — pass the buffer from `import` directly.

---

## Verification

```bash
# Build Rust and deploy
wasm-pack build --target bundler --release --out-dir worker/pkg
wrangler deploy

# Test hash endpoint
curl -X POST https://wasm-worker.<subdomain>.workers.dev \
  -H "Content-Type: text/plain" \
  --data "hello cloudflare"

# Expected: JSON with originalBytes, compressedBytes, ratio, hash

# Check bundle size stays under limit
wrangler deploy --dry-run --outdir dist
du -sh dist/*.wasm
```

---

## Related

- `workers-best-practices.md`
- `workers-resource-limits.md`
- `workers-ai-edge-inference.md`
- `workers-crypto-patterns.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://rustwasm.github.io/docs/wasm-pack/
- https://www.assemblyscript.org/
- https://developers.cloudflare.com/workers/wrangler/bundling/#compiled-wasm
