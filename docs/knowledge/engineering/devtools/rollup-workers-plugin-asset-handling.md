# Rollup Workers Plugin Asset Handling

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Cloudflare Workers project uses Rollup as its bundler (or uses Vite, which drives Rollup
under the hood) and needs to embed static assets — HTML templates, email bodies, WASM modules,
binary files — directly into the Worker bundle as importable strings or `ArrayBuffer`s. The
standard Rollup `@rollup/plugin-url` approach works for browsers but produces `new URL(...)` +
`fetch()` expressions that are meaningless in the Workers runtime, where no DOM and no local
file server exists at runtime.

## Context

Cloudflare Workers bundles run in a V8 isolate: there is no filesystem, no `require.resolve`,
and no CDN from which the Worker can fetch its own static assets. Every asset the Worker needs
at runtime must be *inlined* into the bundle as a literal value or uploaded as a separate
binding (KV, R2, or the `assets` field in `wrangler.toml`).

Rollup's plugin API provides `transform`, `load`, and `resolveId` hooks that make per-extension
inlining straightforward. The challenge is choosing the right encoding (base64 for binary, raw
string for text, `Uint8Array` literal for WASM) and ensuring TypeScript `declare module`
declarations exist so imports type-check.

## 1. Inline Text Assets as ES Module Strings

```typescript
// rollup-plugin-inline-text.ts
import type { Plugin } from "rollup";
import { readFileSync } from "node:fs";

const TEXT_EXTENSIONS = new Set([".html", ".txt", ".sql", ".css", ".svg"]);

export function inlineText(): Plugin {
  return {
    name: "inline-text",
    load(id: string) {
      const ext = id.slice(id.lastIndexOf("."));
      if (!TEXT_EXTENSIONS.has(ext)) return null;

      const content = readFileSync(id, "utf8");
      // Export as a default string — safe for JSON.stringify of arbitrary text
      return `export default ${JSON.stringify(content)};`;
    },
  };
}
```

```typescript
// rollup.config.ts
import { defineConfig } from "rollup";
import typescript from "@rollup/plugin-typescript";
import { inlineText } from "./rollup-plugin-inline-text";

export default defineConfig({
  input: "src/index.ts",
  output: {
    file: "dist/worker.js",
    format: "es",
  },
  plugins: [
    inlineText(),   // Must come before TypeScript so TS sees the resolved module
    typescript(),
  ],
});
```

```typescript
// src/templates/welcome.html  (just a regular file)
// <h1>Welcome, {{name}}!</h1>

// src/index.ts
import welcomeHtml from "./templates/welcome.html";

export default {
  async fetch(request: Request): Promise<Response> {
    const name = new URL(request.url).searchParams.get("name") ?? "World";
    const body = welcomeHtml.replace("{{name}}", name);
    return new Response(body, { headers: { "Content-Type": "text/html" } });
  },
};
```

## 2. TypeScript Declarations for Asset Imports

Without a declaration file TypeScript reports `Cannot find module './templates/welcome.html'`.

```typescript
// src/types/assets.d.ts
declare module "*.html" {
  const content: string;
  export default content;
}

declare module "*.txt" {
  const content: string;
  export default content;
}

declare module "*.svg" {
  const content: string;
  export default content;
}

declare module "*.sql" {
  const content: string;
  export default content;
}

declare module "*.wasm" {
  const bytes: WebAssembly.Module;
  export default bytes;
}
```

```json
// tsconfig.json  (include the declarations)
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true
  },
  "include": ["src/**/*"]
}
```

## 3. Inline Binary Assets as Base64 Strings

```typescript
// rollup-plugin-inline-binary.ts
import type { Plugin } from "rollup";
import { readFileSync } from "node:fs";

const BINARY_EXTENSIONS = new Set([".woff2", ".woff", ".png", ".ico", ".pdf"]);

export function inlineBinary(): Plugin {
  return {
    name: "inline-binary",
    load(id: string) {
      const ext = id.slice(id.lastIndexOf("."));
      if (!BINARY_EXTENSIONS.has(ext)) return null;

      const buffer = readFileSync(id);
      const b64 = buffer.toString("base64");
      const mimeMap: Record<string, string> = {
        ".woff2": "font/woff2",
        ".woff": "font/woff",
        ".png": "image/png",
        ".ico": "image/x-icon",
        ".pdf": "application/pdf",
      };
      const mime = mimeMap[ext] ?? "application/octet-stream";

      // Export both the raw base64 and a data URI for convenience
      return `
const base64 = ${JSON.stringify(b64)};
const dataUri = ${JSON.stringify(`data:${mime};base64,${b64}`)};
export { base64, dataUri };
export default dataUri;
      `.trim();
    },
  };
}
```

```typescript
// src/types/assets.d.ts  (add binary declarations)
declare module "*.woff2" {
  export const base64: string;
  export const dataUri: string;
  const _default: string; // data URI
  export default _default;
}
```

## 4. Inline WASM Modules

Cloudflare Workers supports WebAssembly via `import` when the bundle output format is `es` and
`wrangler` bundles with `--bundle`. However, for custom Rollup pipelines, inline as base64 and
compile at runtime:

```typescript
// rollup-plugin-inline-wasm.ts
import type { Plugin } from "rollup";
import { readFileSync } from "node:fs";

export function inlineWasm(): Plugin {
  return {
    name: "inline-wasm",
    load(id: string) {
      if (!id.endsWith(".wasm")) return null;

      const bytes = readFileSync(id);
      const b64 = bytes.toString("base64");

      // Emit code that compiles the module synchronously from the inlined bytes.
      // Workers supports synchronous WebAssembly.compile.
      return `
const _bytes = Uint8Array.from(atob(${JSON.stringify(b64)}), c => c.charCodeAt(0));
const _module = new WebAssembly.Module(_bytes);
export default _module;
      `.trim();
    },
  };
}
```

```typescript
// src/index.ts
import wasmModule from "./lib/hash.wasm";

let instance: WebAssembly.Instance | null = null;

function getInstance(): WebAssembly.Instance {
  if (!instance) {
    instance = new WebAssembly.Instance(wasmModule, {
      env: { memory: new WebAssembly.Memory({ initial: 1 }) },
    });
  }
  return instance;
}

export default {
  async fetch(request: Request): Promise<Response> {
    const inst = getInstance();
    const hash = (inst.exports.hash as CallableFunction)(42);
    return Response.json({ hash });
  },
};
```

## 5. Vite + Workers: Using `?raw` and `?inline` Suffixes

When using `vite-plugin-cloudflare` or `@cloudflare/vite-plugin`, Vite's built-in query
suffixes handle text and binary assets without a custom plugin:

```typescript
// src/index.ts  (Vite project)
// ?raw imports the file as a string (Vite built-in)
import welcomeHtml from "./templates/welcome.html?raw";
// ?url is inlined as a data URI by vite-plugin-cloudflare
import logoDataUri from "./assets/logo.png?inline";

export default {
  async fetch(): Promise<Response> {
    return new Response(welcomeHtml, {
      headers: { "Content-Type": "text/html" },
    });
  },
};
```

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import { cloudflare } from "@cloudflare/vite-plugin";

export default defineConfig({
  plugins: [cloudflare()],
  // Ensure ?raw imports are not processed further by other plugins
  assetsInclude: [],
});
```

## 6. Bundle Size Check After Asset Inlining

```typescript
// scripts/check-bundle-size.ts
import { statSync } from "node:fs";

const MAX_WORKER_BUNDLE_BYTES = 1_024 * 1_024; // 1 MiB (compressed limit is 1 MiB)
const bundlePath = "dist/worker.js";

const { size } = statSync(bundlePath);
if (size > MAX_WORKER_BUNDLE_BYTES) {
  console.error(
    `Bundle too large: ${(size / 1024).toFixed(1)} KiB > ${MAX_WORKER_BUNDLE_BYTES / 1024} KiB`
  );
  process.exit(1);
}
console.log(`Bundle size OK: ${(size / 1024).toFixed(1)} KiB`);
```

```json
// package.json
{
  "scripts": {
    "build": "rollup -c rollup.config.ts --configPlugin typescript",
    "postbuild": "tsx scripts/check-bundle-size.ts"
  }
}
```

## Anti-patterns

- **Using `@rollup/plugin-url` without `limit: Infinity`** — emits `new URL(asset, import.meta.url)`
  which resolves to `undefined` in Workers (no `import.meta.url` filesystem path).
- **Importing large binary assets as strings** — base64 encoding inflates by ~33%; use KV or R2
  for files over ~100 KiB. The Workers compressed bundle limit is 1 MiB.
- **Forgetting the `declare module` block** — TypeScript builds succeed in `skipLibCheck` mode
  but IDE hover and go-to-definition break silently.
- **Using `process.cwd()` inside the plugin's `load` hook** — Rollup resolves IDs to absolute
  paths; always use the `id` parameter directly with `readFileSync(id)`.

## Gotchas

- Rollup calls `load` with the *resolved* absolute path. If `resolveId` is not implemented, the
  plugin must rely on Rollup's default resolution and match on `id` file extension only.
- `JSON.stringify` of file content correctly escapes backticks, Unicode, and control characters,
  making it safer than template literals for arbitrary binary-as-text.
- `@cloudflare/vite-plugin`'s `?inline` is not the same as Vite's native `?url`; the plugin
  converts `?url` imports to data URIs in Workers context automatically, but only for asset
  types listed in `assetsInclude`.
- Wrangler's `--bundle` flag (enabled by default) runs its own esbuild pass after Rollup. If
  both Rollup and esbuild see the same `.wasm` import, the asset may be double-processed.

## Verification

```bash
# Confirm all asset imports are inlined as string literals, not file references
grep -E "new URL|import\.meta\.url" dist/worker.js && echo "FAIL: live URL reference found" || echo "OK"

# Check final bundle size
du -sh dist/worker.js

# Smoke-test in local dev that assets load correctly
wrangler dev --local --port 8787 &
curl -s http://localhost:8787/ | head -5
```

## Related

- `esbuild-workers-plugins-custom-transforms.md`
- `vite-workers-build-plugin-custom.md`
- `vite-cloudflare-workers-dev-mode.md`
- `esbuild-metafile-bundle-analysis-workers.md`
- `production-source-maps-strategy.md`

## Sources

- https://rollupjs.org/plugin-development/#load
- https://developers.cloudflare.com/workers/reference/security-model/
- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://vitejs.dev/guide/assets.html#importing-asset-as-string
- https://github.com/cloudflare/workers-sdk/tree/main/packages/vite-plugin
