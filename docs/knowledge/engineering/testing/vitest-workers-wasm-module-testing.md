# Vitest Workers WebAssembly Module Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a Cloudflare Worker that imports a `.wasm` file — image processing, crypto primitives, a compiled Rust or C++ library — and tests fail because the Workers runtime's WASM instantiation path is not available in a plain Node.js Jest or Vitest environment. You need deterministic unit tests that exercise the wasm module's exported functions while keeping the suite fast.

## Context

Cloudflare Workers support WebAssembly modules as first-class bindings. A module imported with `import wasmModule from './lib.wasm'` resolves to a `WebAssembly.Module` instance at runtime; calling `new WebAssembly.Instance(wasmModule, imports)` gives you the exports. `@cloudflare/vitest-pool-workers` runs tests inside a real Workers runtime (via Miniflare), so the same WASM lifecycle your production code uses is available in tests without mocking. The key configuration step is declaring the `.wasm` file as a module rule in `wrangler.toml` so the pool picks it up.

## Configuring wrangler.toml for WASM modules

```toml
# wrangler.toml
name = "wasm-worker"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[rules]]
type = "CompiledWasm"
globs = ["**/*.wasm"]
fallthrough = false
```

```ts
// vitest.config.ts
import { defineConfig } from "vitest/config";
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

## Writing a Worker that uses a WASM module

```ts
// src/index.ts
import wasmModule from "./hash.wasm";

let instance: WebAssembly.Instance | null = null;

async function getInstance(): Promise<WebAssembly.Instance> {
  if (!instance) {
    instance = await WebAssembly.instantiate(wasmModule, {});
  }
  return instance;
}

export default {
  async fetch(request: Request): Promise<Response> {
    const inst = await getInstance();
    const exports = inst.exports as { hash32: (n: number) => number };

    const url = new URL(request.url);
    const input = parseInt(url.searchParams.get("n") ?? "0", 10);
    const result = exports.hash32(input);

    return Response.json({ input, hash: result });
  },
} satisfies ExportedHandler;
```

## Unit-testing the WASM exports directly

```ts
// src/index.test.ts
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import wasmModule from "./hash.wasm";
import worker from "./index";

describe("hash.wasm exports", () => {
  it("instantiates and exports hash32", async () => {
    const inst = await WebAssembly.instantiate(wasmModule, {});
    const { hash32 } = inst.exports as { hash32: (n: number) => number };
    expect(typeof hash32).toBe("function");
  });

  it("hash32 is deterministic", async () => {
    const inst = await WebAssembly.instantiate(wasmModule, {});
    const { hash32 } = inst.exports as { hash32: (n: number) => number };
    expect(hash32(42)).toBe(hash32(42));
  });

  it("hash32 differs for different inputs", async () => {
    const inst = await WebAssembly.instantiate(wasmModule, {});
    const { hash32 } = inst.exports as { hash32: (n: number) => number };
    expect(hash32(1)).not.toBe(hash32(2));
  });
});
```

## Integration-testing the Worker fetch handler

```ts
// src/index.test.ts (continued)
describe("Worker fetch handler", () => {
  it("returns hash for a given input", async () => {
    const ctx = createExecutionContext();
    const request = new Request("https://example.com/?n=7");
    const response = await worker.fetch(request, env, ctx);
    await waitOnExecutionContext(ctx);

    expect(response.status).toBe(200);
    const body = await response.json<{ input: number; hash: number }>();
    expect(body.input).toBe(7);
    expect(typeof body.hash).toBe("number");
  });

  it("defaults to n=0 when param is absent", async () => {
    const ctx = createExecutionContext();
    const request = new Request("https://example.com/");
    const response = await worker.fetch(request, env, ctx);
    await waitOnExecutionContext(ctx);

    const body = await response.json<{ input: number; hash: number }>();
    expect(body.input).toBe(0);
  });
});
```

## Testing WASM with shared memory or SIMD features

```ts
// src/simd.test.ts
import { it, expect } from "vitest";
import simdModule from "./simd_sum.wasm";

it("WASM SIMD dot product matches scalar", async () => {
  // Workers runtime supports WASM SIMD; verify parity with a JS reference
  const inst = await WebAssembly.instantiate(simdModule, {});
  const exports = inst.exports as {
    memory: WebAssembly.Memory;
    dot_product: (aPtr: number, bPtr: number, len: number) => number;
  };

  const mem = new Float32Array(exports.memory.buffer);
  const aPtr = 0;
  const bPtr = 16;
  const len = 4;

  // Write vectors at byte offsets 0 and 64
  mem.set([1, 2, 3, 4], aPtr / 4);
  mem.set([5, 6, 7, 8], bPtr / 4);

  const wasmResult = exports.dot_product(aPtr, bPtr, len);
  const jsResult = [1, 2, 3, 4].reduce((s, v, i) => s + v * [5, 6, 7, 8][i], 0);

  expect(wasmResult).toBeCloseTo(jsResult, 5);
});
```

## Anti-patterns

- **Mocking `WebAssembly.instantiate` with a stub object** — you lose all type safety and skip the actual binary execution. Use the real pool-workers runtime instead.
- **Sharing a singleton module instance across test files** — WASM instances can hold mutable linear memory; parallel tests will corrupt each other. Instantiate per-test or per-suite.
- **Checking in `.wasm` binaries as fixtures** — build them deterministically from source in CI so the binary under test matches the code under review.
- **Using `fetch` to load `.wasm` at test time** — the module binding (`import wasmModule from './x.wasm'`) is the correct Workers pattern; dynamic fetch is for browser contexts.

## Gotchas

- `WebAssembly.instantiate(module, importObject)` is the two-argument form that accepts a pre-compiled `WebAssembly.Module`. In Node.js environments you often pass a `BufferSource`; in Workers you pass the compiled module directly — the overload differs.
- WASM linear memory starts at zero and is not reset between calls. If your function writes to memory, reset it before assertions that depend on a clean state.
- The `CompiledWasm` rule in `wrangler.toml` is required for the pool to expose the module binding; without it the import resolves to `undefined` even in the Workers pool environment.
- `wasm-bindgen`-generated glue code requires matching JS shims. Import the shim alongside the `.wasm` file and ensure the shim is also bundled (add it to `[[rules]]` as `ESModule` if needed).

## Verification

```bash
# Run only WASM tests
npx vitest run --reporter=verbose src/**/*.wasm*.test.ts

# Confirm the .wasm file is picked up by the pool
npx wrangler deploy --dry-run --outdir dist && ls dist/*.wasm
```

Expected: all WASM tests pass; `dist/` contains the `.wasm` artifact confirming the rule matched.

## Related

- `vitest-workers-ai-text-embedding-integration-testing.md`
- `workers-test-patterns.md`
- `vitest-cloudflare-pool-workers.md`
- `vitest-workers-env-var-override-testing.md`

## Sources

- Cloudflare Docs — WebAssembly in Workers: https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- `@cloudflare/vitest-pool-workers` README: https://github.com/cloudflare/workers-sdk/tree/main/packages/vitest-pool-workers
- Cloudflare Docs — Module rules (wrangler.toml): https://developers.cloudflare.com/workers/wrangler/configuration/#module-rules
- WebAssembly JS API spec — `WebAssembly.instantiate`: https://webassembly.github.io/spec/js-api/#dom-webassembly-instantiate-moduleobject-importobject
