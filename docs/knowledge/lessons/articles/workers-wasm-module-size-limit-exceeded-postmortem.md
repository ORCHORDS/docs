# Workers WASM Module Size Limit Exceeded Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Deployment of a Workers script that embedded a compiled WebAssembly module failed with:

```
Error: Script startup exceeded CPU time limit.
Script size: 3.2 MB (limit: 1 MB for free / 10 MB compressed for paid plans).
WASM module instantiation failed: module too large.
```

The error surfaced only on `wrangler deploy`, not during local `wrangler dev`, because Miniflare's WASM handling does not enforce the production size budget. A three-hour release window was missed.

## Context

The team added a Rust-compiled WASM binary for fast server-side image resizing (thumbnail generation). The `.wasm` file was 4.1 MB uncompressed, 1.9 MB gzip-compressed. Workers enforces a **1 MB compressed** limit on the total *script bundle* (Worker code + all WASM modules) on paid plans when the legacy format is used, and a **10 MB compressed** limit for ES module Workers using the `[wasm_modules]` or `[[rules]]` binding. The team was on a legacy Service Worker format.

The build pipeline did not include a bundle-size gate, so the overage was invisible until deploy.

## 1. Understanding the Two Format Limits

Workers has different limits depending on the script format:

| Format | Compressed limit | WASM binding mechanism |
|---|---|---|
| Service Worker (legacy) | 1 MB | `WebAssembly.instantiateStreaming(fetch(...))` at runtime |
| ES Modules (current) | 10 MB | `[[rules]] type = "CompiledWasm"` in `wrangler.toml` |

Migrating from Service Worker to ES Module format unlocks the larger budget and is the recommended path.

## 2. Migrating to ES Module Format

**wrangler.toml before (Service Worker):**
```toml
name = "image-resizer"
main = "src/worker.js"
compatibility_date = "2026-01-01"
```

**wrangler.toml after (ES Modules with WASM binding):**
```toml
name = "image-resizer"
main = "src/worker.ts"
compatibility_date = "2026-01-01"

[[rules]]
type = "CompiledWasm"
globs = ["**/*.wasm"]
fallthrough = false
```

**src/worker.ts:**
```typescript
import wasmModule from "./resizer.wasm";

interface Env {}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const instance = await WebAssembly.instantiate(wasmModule);
    const exports = instance.exports as { resize: (w: number, h: number) => number };
    const result = exports.resize(320, 240);
    return new Response(`Resized: ${result}`);
  },
};
```

## 3. Adding a Bundle-Size Gate to CI

Add a size check before `wrangler deploy` so the overage is caught locally and in CI:

```bash
#!/usr/bin/env bash
# scripts/check-wasm-size.sh
set -euo pipefail

MAX_BYTES=$((9 * 1024 * 1024))   # 9 MB — leave headroom below the 10 MB limit
WASM_FILE="src/resizer.wasm"

SIZE=$(gzip -c "$WASM_FILE" | wc -c)
echo "Compressed WASM size: ${SIZE} bytes (limit ${MAX_BYTES})"

if [[ "$SIZE" -gt "$MAX_BYTES" ]]; then
  echo "ERROR: WASM module exceeds size budget" >&2
  exit 1
fi
```

```yaml
# .github/workflows/deploy.yml (excerpt)
- name: Check WASM size
  run: bash scripts/check-wasm-size.sh

- name: Deploy Worker
  run: npx wrangler deploy
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## 4. Shrinking the WASM Binary

If migration to ES Modules is not immediately possible, reduce the `.wasm` size:

```toml
# Cargo.toml — enable optimizations that cut WASM size ~30-60%
[profile.release]
opt-level = "z"      # optimize for size
lto = true
codegen-units = 1
panic = "abort"
strip = true
```

```bash
# After cargo build --release --target wasm32-unknown-unknown
# Run wasm-opt for an additional 10-30% reduction
wasm-opt -Oz \
  target/wasm32-unknown-unknown/release/resizer.wasm \
  -o src/resizer.wasm
```

Check size before and after:

```typescript
// scripts/bundle-report.ts
import { statSync } from "fs";
import { gzipSync } from "zlib";
import { readFileSync } from "fs";

const raw = readFileSync("src/resizer.wasm");
const compressed = gzipSync(raw);
console.log(`Raw:        ${(raw.length / 1024).toFixed(1)} KB`);
console.log(`Compressed: ${(compressed.length / 1024).toFixed(1)} KB`);
console.log(`Ratio:      ${((1 - compressed.length / raw.length) * 100).toFixed(1)}%`);
```

## 5. Runtime Lazy-Load Fallback (Edge-Cache Pattern)

For WASM modules that cannot be shrunk below the 10 MB limit, fetch from R2 and cache in the worker's module cache:

```typescript
// This pattern works only when the WASM itself can be fetched at runtime.
// It trades cold-start latency for bundle size.
let cachedModule: WebAssembly.Module | null = null;

export default {
  async fetch(request: Request, env: { WASM_BUCKET: R2Bucket }): Promise<Response> {
    if (!cachedModule) {
      const obj = await env.WASM_BUCKET.get("resizer.wasm");
      if (!obj) throw new Error("WASM binary not found in R2");
      const bytes = await obj.arrayBuffer();
      cachedModule = await WebAssembly.compile(bytes);
    }
    const instance = await WebAssembly.instantiate(cachedModule);
    // ... use instance
    return new Response("ok");
  },
};
```

Note: `WebAssembly.compile` at runtime counts against CPU time. Prefer the `[[rules]]` binding approach.

## Anti-patterns

- Embedding WASM in a legacy Service Worker format without checking compressed size.
- Relying on `wrangler dev` / Miniflare to surface production size limits — it does not.
- Using `wasm-pack` defaults (`pkg` target) which includes JS glue that inflates the bundle; use `--target no-modules` or `--target bundler` and tree-shake the glue.
- Fetching WASM from a public URL at runtime — that counts as a subrequest and adds cold-start latency; use R2 or the `[[rules]]` binding.

## Gotchas

- The 10 MB limit is on the **compressed** bundle, not each file individually. All WASM modules in the Worker are summed together.
- `wasm-opt` must be run on the final linked `.wasm`, not on intermediate object files.
- Workers' `WebAssembly.instantiateStreaming` requires a `Response` with `Content-Type: application/wasm`. If you serve from R2 without setting the content type the call throws.
- Durable Objects have the same 10 MB compressed limit as the Worker that hosts them.

## Verification

```bash
# Confirm deploy succeeds with size under budget
npx wrangler deploy --dry-run 2>&1 | grep -E "Script size|Error"

# Confirm WASM binding resolves correctly in production
curl -sf https://image-resizer.example.workers.dev/health | jq .wasm_loaded
```

## Related

- workers-script-size-limit-exceeded.md
- workers-memory-128mb-limit-oom-postmortem.md
- r2-multipart-upload-size-limit-lesson.md

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://developers.cloudflare.com/workers/wasm-modules/
- https://rustwasm.github.io/wasm-pack/book/
