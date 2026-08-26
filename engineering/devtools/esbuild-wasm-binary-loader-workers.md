# esbuild WASM and Binary Asset Loader Plugin for Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a `.wasm` module (e.g., a compression library, a custom codec, or a cryptographic
primitive) that needs to be bundled into a Cloudflare Worker. esbuild's built-in
`loader: { '.wasm': 'binary' }` option and the Workers-specific `wasm_modules` binding in
`wrangler.toml` serve different use-cases. You want an esbuild plugin that either:
- Inlines the WASM as a base64 `Uint8Array` for small payloads, or
- Emits it as a separate file and returns a `WebAssembly.Module` via wrangler module rules

## Context

Workers supports three WASM instantiation patterns: (1) top-level `wasm_modules` binding —
the runtime pre-compiles the `.wasm` and injects a `WebAssembly.Module` as an environment
binding; (2) dynamic `fetch` + `WebAssembly.compileStreaming` — not available in Workers
because `fetch` of local assets requires a KV or R2 binding; (3) static import of a `.wasm`
file when using `wrangler`'s built-in module rules (`type = "CompiledWasm"`). An esbuild
plugin fills the gap when you build outside `wrangler`'s bundler (e.g., in a custom CI
pipeline) or need conditional WASM loading based on environment.

## 1. wrangler.toml Module Rules (Preferred Simple Path)

For most cases, use wrangler's built-in module rule — no esbuild plugin needed:

```toml
# wrangler.toml
name = "wasm-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[rules]]
type = "CompiledWasm"
globs = ["**/*.wasm"]
fallthrough = false
```

```typescript
// src/index.ts
import wasmModule from './codec.wasm';  // typed as WebAssembly.Module

let instance: WebAssembly.Instance | null = null;

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    instance ??= await WebAssembly.instantiate(wasmModule, {});
    const exports = instance.exports as { compress: (n: number) => number };
    return Response.json({ result: exports.compress(42) });
  },
};
```

## 2. Custom esbuild Plugin: Base64 Inline Loader

When building with a custom esbuild script instead of `wrangler build`, inline small WASM
files as base64 `Uint8Array`:

```typescript
// build/plugins/wasm-inline-loader.ts
import type { Plugin } from 'esbuild';
import { readFileSync } from 'node:fs';

/**
 * Loads .wasm files as a base64-decoded Uint8Array.
 * Suitable for WASM modules < 100 KB where binary size is acceptable inline.
 */
export const wasmInlineLoader: Plugin = {
  name: 'wasm-inline-loader',
  setup(build) {
    build.onLoad({ filter: /\.wasm$/ }, async (args) => {
      const bytes = readFileSync(args.path);
      const base64 = bytes.toString('base64');
      const contents = `
        const base64 = "${base64}";
        const binary  = atob(base64);
        const bytes   = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        export default bytes.buffer;
      `;
      return { contents, loader: 'js' };
    });
  },
};
```

```typescript
// build/build.ts
import esbuild from 'esbuild';
import { wasmInlineLoader } from './plugins/wasm-inline-loader';

await esbuild.build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  outfile: 'dist/worker.js',
  platform: 'browser',
  target: 'es2022',
  format: 'esm',
  plugins: [wasmInlineLoader],
});
```

## 3. Custom esbuild Plugin: Compiled Module Emitter

For larger WASM files, emit the `.wasm` as a side-output and re-export it as a
`WebAssembly.Module` using a synchronous top-level `await` pattern:

```typescript
// build/plugins/wasm-module-loader.ts
import type { Plugin } from 'esbuild';
import { readFileSync } from 'node:fs';
import { copyFileSync, mkdirSync } from 'node:fs';
import { basename, join, dirname } from 'node:path';

export const wasmModuleLoader: Plugin = {
  name: 'wasm-module-loader',
  setup(build) {
    build.onLoad({ filter: /\.wasm$/ }, (args) => {
      const filename  = basename(args.path);
      const outDir    = build.initialOptions.outdir ?? dirname(build.initialOptions.outfile ?? '.');
      mkdirSync(outDir, { recursive: true });
      copyFileSync(args.path, join(outDir, filename));

      // Emit a JS proxy that re-exports a compiled module via module import
      // Workers handles the static import of .wasm when rules are configured
      const contents = `
        // This import is rewritten by wrangler's module resolver at deploy time
        import wasmModule from './${filename}';
        export default wasmModule;
      `;
      return { contents, loader: 'js' };
    });
  },
};
```

## 4. TypeScript Declaration for .wasm Imports

Prevent `TS2307: Cannot find module '*.wasm'` errors:

```typescript
// src/types/wasm.d.ts
declare module '*.wasm' {
  const module: WebAssembly.Module;
  export default module;
}
```

Add to `tsconfig.json`:

```jsonc
{
  "compilerOptions": {
    "typeRoots": ["./src/types", "./node_modules/@types"]
  }
}
```

## 5. Instantiation Pattern in Workers

Instantiate once per isolate using a module-scope variable to avoid re-compilation cost on
every request:

```typescript
// src/index.ts
import wasmBuffer from './codec.wasm'; // ArrayBuffer (inline loader) or Module (module loader)

// Normalise to WebAssembly.Module
const wasmMod: WebAssembly.Module =
  wasmBuffer instanceof WebAssembly.Module
    ? wasmBuffer
    : new WebAssembly.Module(wasmBuffer);

// Instantiate lazily — Workers may snapshot the isolate before first request
let _instance: WebAssembly.Instance | null = null;

async function getInstance(): Promise<WebAssembly.Instance> {
  if (!_instance) {
    _instance = await WebAssembly.instantiate(wasmMod, { env: {} });
  }
  return _instance;
}

export default {
  async fetch(req: Request): Promise<Response> {
    const inst    = await getInstance();
    const exports = inst.exports as WasmExports;
    return Response.json({ ok: true, value: exports.run(1) });
  },
};

interface WasmExports {
  run(n: number): number;
  memory: WebAssembly.Memory;
}
```

## 6. Vitest Test for the WASM Integration

```typescript
// src/codec.test.ts
import { describe, it, expect, vi } from 'vitest';

// Mock the WASM import so tests don't need the real binary
vi.mock('./codec.wasm', () => ({
  default: new WebAssembly.Module(
    // minimal valid WASM: magic + version only (exports nothing — extend as needed)
    new Uint8Array([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00]).buffer,
  ),
}));

describe('WASM integration', () => {
  it('instantiates without throwing', async () => {
    const { getInstance } = await import('./index');
    const inst = await getInstance();
    expect(inst).toBeInstanceOf(WebAssembly.Instance);
  });
});
```

## Anti-patterns

- **`loader: { '.wasm': 'file' }` in esbuild standalone builds** — this emits the `.wasm`
  as a content-hashed asset and rewrites the import to a string path. Workers cannot
  `fetch()` local paths at runtime; the path resolves to nothing.
- **`WebAssembly.compileStreaming(fetch('/codec.wasm'))`** — Workers does not serve static
  files from the bundle via `fetch`. Use module rules or inline loading instead.
- **Re-instantiating WASM on every request** — `WebAssembly.instantiate` is expensive
  (~5–50 ms). Cache the `WebAssembly.Instance` in module scope.
- **Exceeding the 1 MB compressed bundle limit** — WASM binaries count toward the Worker
  bundle size. Inline base64 inflates the JS payload by ~33%; prefer the module emitter
  plugin for files > 50 KB.

## Gotchas

- `WebAssembly.Module` constructor is **synchronous** but not allowed in the global scope
  of a Worker if the WASM binary is > 128 KB — the runtime enforces this limit. Use
  `WebAssembly.compile(buffer)` (async) for large modules.
- The base64 inline approach embeds the binary in the JS bundle; this bypasses wrangler's
  module system entirely and is invisible to `wrangler types` generation.
- When using `wrangler dev --remote` with `[[rules]] type = "CompiledWasm"`, the WASM is
  uploaded to Cloudflare's edge and compiled there. Local dev compiles it in Node via
  `@cloudflare/workerd` which may report different compile errors than production.

## Verification

```bash
# Confirm .wasm appears in bundle output (inline loader)
esbuild src/index.ts --bundle --analyze 2>&1 | grep -i wasm

# Confirm no 'file' loader references survive in the output
grep -n 'file://' dist/worker.js && echo "BAD: file:// reference found" || echo "OK"

# Wrangler deploy dry-run validates module rules
wrangler deploy --dry-run --outdir dist-check
ls dist-check/*.wasm  # should exist if using module emitter
```

## Related

- `esbuild-workers-plugins-custom-transforms.md`
- `esbuild-external-packages-workers-bundle.md`
- `workers-dynamic-import-code-splitting-strategy.md`
- `wrangler-config-jsonc-toml-migration.md`

## Sources

- Cloudflare Workers WASM docs — https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- esbuild loader docs — https://esbuild.github.io/content-types/#wasm
- WebAssembly.Module (MDN) — https://developer.mozilla.org/en-US/docs/WebAssembly/JavaScript_interface/Module
- Wrangler module rules — https://developers.cloudflare.com/workers/wrangler/configuration/#module-rules
