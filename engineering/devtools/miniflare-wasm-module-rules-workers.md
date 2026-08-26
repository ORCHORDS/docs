# Miniflare WASM Custom Module Rules for Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker imports a `.wasm` file directly, and when you run tests
via `vitest-pool-workers` or the `Miniflare` programmatic API you get one of:

```
Error: Cannot find module './lib/encoder.wasm'
Error: Imported module must be a WebAssembly.Module
ReferenceError: WebAssembly is not defined in this environment
```

Wrangler handles `.wasm` imports transparently during `wrangler dev` / `wrangler
deploy`, but the local test runtime needs explicit **module rules** that tell
Miniflare how to resolve and type each non-JS import.

---

## Context

Cloudflare Workers supports three non-standard import kinds beyond ES modules:

| Import kind  | wrangler.toml `type` | Received by Worker |
|-------------|---------------------|--------------------|
| `.wasm`     | `CompiledWasm`      | `WebAssembly.Module` |
| `.bin`      | `Data`              | `ArrayBuffer`       |
| `.txt`      | `Text`              | `string`            |

Miniflare v3/v4 mirrors this through its `moduleRules` option. Without the
correct rule the module bundler either throws at import time or hands the
Worker a `string` path instead of a compiled module object.

The feature is documented in the Workers Runtime API docs under **Module
Workers** and in Miniflare's source as `ModuleRuleType`.

---

## Configuring Module Rules in wrangler.toml

```toml
# wrangler.toml
name = "wasm-demo"
compatibility_date = "2024-09-23"

[[rules]]
type = "CompiledWasm"
globs = ["**/*.wasm"]
fallthrough = false

[[rules]]
type = "Data"
globs = ["**/*.bin"]
fallthrough = false

[[rules]]
type = "Text"
globs = ["**/*.txt"]
fallthrough = false
```

Wrangler reads these rules at build time. Miniflare must receive the same
rules when running without Wrangler.

---

## Programmatic Miniflare Setup (Unit Tests)

```typescript
// test/setup.miniflare.ts
import { Miniflare, Log, LogLevel } from "miniflare";
import path from "node:path";

export function createMiniflare() {
  return new Miniflare({
    log: new Log(LogLevel.WARN),
    // Point at the Worker entry point
    scriptPath: path.resolve(__dirname, "../dist/worker.js"),
    modules: true,
    // Mirror wrangler.toml [[rules]]
    moduleRules: [
      { type: "CompiledWasm", include: ["**/*.wasm"] },
      { type: "Data",         include: ["**/*.bin"]  },
      { type: "Text",         include: ["**/*.txt"]  },
    ],
    // Bindings remain optional alongside module rules
    kvNamespaces: ["KV"],
    compatibilityDate: "2024-09-23",
  });
}
```

---

## Worker Code Pattern

```typescript
// src/worker.ts
import encoderWasm from "./lib/encoder.wasm";   // WebAssembly.Module
import defaultDict from "./data/words.bin";      // ArrayBuffer
import helpText    from "./copy/help.txt";       // string

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Instantiate WASM — the module is already compiled by the runtime
    const instance = await WebAssembly.instantiate(encoderWasm, {
      env: { memory: new WebAssembly.Memory({ initial: 1 }) },
    });

    const encode = instance.exports.encode as (n: number) => number;

    return new Response(
      JSON.stringify({
        encoded: encode(42),
        dictBytes: defaultDict.byteLength,
        help: helpText.slice(0, 80),
      }),
      { headers: { "content-type": "application/json" } }
    );
  },
} satisfies ExportedHandler<Env>;
```

---

## Vitest Pool Workers Integration

When using `@cloudflare/vitest-pool-workers`, module rules go inside the
`poolOptions` block of `vitest.config.ts`:

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        // Override or supplement wrangler.toml rules for the test pool
        miniflare: {
          moduleRules: [
            { type: "CompiledWasm", include: ["**/*.wasm"] },
            { type: "Data",         include: ["**/*.bin"]  },
            { type: "Text",         include: ["**/*.txt"]  },
          ],
        },
      },
    },
  },
});
```

> Note: when `wrangler.configPath` is set, Miniflare already reads `[[rules]]`
> from `wrangler.toml`. You only need the explicit `miniflare.moduleRules` key
> when your test setup does **not** use a `wrangler.toml`, or when you need
> additional rules not present there.

---

## Writing Tests Against WASM Imports

```typescript
// test/encoder.test.ts
import { env, createExecutionContext, waitOnExecutionContext }
  from "cloudflare:test";
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { createMiniflare } from "./setup.miniflare";
import type { Miniflare } from "miniflare";

let mf: Miniflare;

beforeAll(async () => {
  mf = createMiniflare();
  await mf.ready;
});

afterAll(async () => {
  await mf.dispose();
});

describe("WASM encoder", () => {
  it("returns an encoded value", async () => {
    const res = await mf.dispatchFetch("http://localhost/");
    const body = await res.json<{ encoded: number }>();
    expect(body.encoded).toBeTypeOf("number");
  });

  it("includes dictBytes", async () => {
    const res = await mf.dispatchFetch("http://localhost/");
    const body = await res.json<{ dictBytes: number }>();
    expect(body.dictBytes).toBeGreaterThan(0);
  });
});
```

---

## TypeScript Type Declarations for Non-JS Imports

Without ambient declarations tsc will error on `import foo from './file.wasm'`.
Add a declarations file:

```typescript
// src/types/modules.d.ts

// .wasm imports → already-compiled WebAssembly.Module
declare module "*.wasm" {
  const module: WebAssembly.Module;
  export default module;
}

// .bin imports → ArrayBuffer
declare module "*.bin" {
  const buffer: ArrayBuffer;
  export default buffer;
}

// .txt imports → string
declare module "*.txt" {
  const content: string;
  export default content;
}
```

Include this file in `tsconfig.json`:

```json
{
  "compilerOptions": { "moduleResolution": "bundler" },
  "include": ["src", "src/types"]
}
```

---

## Anti-patterns

- **Omitting `modules: true`** in the Miniflare constructor. Without this flag
  Miniflare treats the script as a Service Worker and WASM imports are silently
  ignored or mis-typed.
- **Relying on `wrangler dev` behavior in tests** without reproducing `[[rules]]`
  in the Miniflare config. Wrangler builds the bundle first; Miniflare receives
  a pre-built file and needs the rules to interpret the embedded asset URLs.
- **Using `fallthrough: true`** on `CompiledWasm` without a catch-all rule.
  Fallthrough causes Miniflare to try the next rule; if none matches, it falls
  back to treating the file as a plain ES module, which fails at runtime.
- **Bundling the `.wasm` file as base64 with esbuild** and then expecting
  Miniflare's WASM rule to intercept it. When esbuild inlines the binary the
  Workers runtime never sees the original import; skip esbuild's `dataUrlLoader`
  for `.wasm` and let Wrangler handle it.

---

## Gotchas

- Miniflare v3 added `moduleRules`; Miniflare v2 used `wasmBindings`, which is
  a completely different API (KV-style binding, not import-based). Do not mix
  the two.
- `WebAssembly.instantiateStreaming` is **not** available in the local Miniflare
  runtime for file-based modules — use `WebAssembly.instantiate(module, imports)`
  directly.
- WASM file paths inside `dist/` must be preserved relative to the Worker
  bundle. If you run esbuild and it flattens the directory, the module rule
  glob `**/*.wasm` may still match, but the resolved path may differ from what
  the Worker code expects.
- Large WASM files (>1 MB) slow local test startup because Miniflare compiles
  them synchronously on each cold boot. Consider stubbing heavy WASM in unit
  tests and reserving the real binary for integration tests.

---

## Verification

```bash
# 1. Confirm rules are parsed from wrangler.toml
wrangler types --dry-run 2>&1 | grep -i wasm

# 2. Run the test suite — no "Cannot find module *.wasm" errors
pnpm vitest run

# 3. Inspect the Miniflare module registry in DEBUG mode
MINIFLARE_LOG=DEBUG pnpm vitest run 2>&1 | grep -i "module rule"

# 4. Validate the Worker in wrangler dev
wrangler dev --local 2>&1 | grep -i wasm
```

---

## Related

- `miniflare-d1-test-seeding-fixtures.md`
- `miniflare-durable-objects-fake-clock-testing.md`
- `vitest-pool-workers-cloudflare-test-api.md`
- `esbuild-workers-plugins-custom-transforms.md`
- `typescript-workers-env-interface-module-augmentation.md`

---

## Sources

- https://developers.cloudflare.com/workers/wrangler/configuration/#bundling
- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://github.com/cloudflare/workers-sdk/tree/main/packages/miniflare
- https://miniflare.dev/get-started/module-worker
- https://developers.cloudflare.com/workers/languages/webassembly/
