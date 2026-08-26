# Workers Bundle Size Optimization Tree Shaking

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A example project Worker that imports large utility libraries (lodash, date-fns, zod, jose) bloats past
the 1 MB compressed bundle limit, causing deploy failures and inflated cold-start parse time on
the V8 isolate. Even below the limit, every extra KB delays isolate start for anonymous users
hitting a cold route for the first time.

## Context

Cloudflare Workers uses an esbuild-based bundler (via Wrangler) that performs tree-shaking on
ES-module graphs. However, CommonJS imports, barrel re-exports, and dynamic `require()` calls
defeat the shaker. The Workers runtime also imposes a 10 ms CPU budget for isolate startup, so
parse overhead from dead code counts against real request latency.

## Section 1 — Measure Current Bundle Composition

Use Wrangler's built-in metafile flag to emit an esbuild analysis JSON, then feed it to the
bundle-wizard or esbuild-bundle-analyzer to pinpoint offending modules.

```typescript
// wrangler.toml addition
// [build]
// command = "npx esbuild src/index.ts --bundle --metafile=meta.json --format=esm"

// scripts/analyze-bundle.ts
import { execSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";

interface MetaModule {
  bytes: number;
  imports: { path: string }[];
}
interface EsbuildMeta {
  inputs: Record<string, MetaModule>;
}

const meta: EsbuildMeta = JSON.parse(readFileSync("meta.json", "utf8"));

const sorted = Object.entries(meta.inputs)
  .map(([path, info]) => ({ path, bytes: info.bytes }))
  .sort((a, b) => b.bytes - a.bytes)
  .slice(0, 20);

console.table(sorted.map((m) => ({ ...m, kb: (m.bytes / 1024).toFixed(1) })));
```

Running `npx wrangler deploy --dry-run --outdir dist` then examining `dist/*.js` with
`wc -c` gives the compressed size Cloudflare enforces.

## Section 2 — Replace Barrel Imports with Deep Imports

The single most effective tree-shaking fix is replacing barrel-file imports with direct module
paths. Barrel re-exports force the bundler to include the entire package even when only one
function is used.

```typescript
// ❌ Before — pulls all of jose into the bundle
import { SignJWT, jwtVerify } from "jose";

// ✅ After — only the two used modules
import { SignJWT } from "jose/jwt/sign";
import { jwtVerify } from "jose/jwt/verify";

// ❌ Before — entire lodash (70 KB min)
import _ from "lodash";
const slug = _.kebabCase(title);

// ✅ After — 1 KB
import kebabCase from "lodash-es/kebabCase.js";
const slug = kebabCase(title);

// ❌ Before — all of zod validators
import { z } from "zod";

// ✅ After — mark zod as external and validate at edge with native patterns,
//    or keep zod but use modular import paths once zod v4 ships esm tree-shakeable build
import { z } from "zod/v4"; // zod v4 ships per-module esm
```

## Section 3 — Wrangler / esbuild Configuration for Aggressive Shaking

Fine-tune esbuild options exposed through `wrangler.toml` and a custom build script to
maximise dead code elimination in the example project Worker bundle.

```typescript
// build.ts — custom esbuild wrapper called by wrangler build.command
import * as esbuild from "esbuild";

await esbuild.build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  format: "esm",
  target: "es2022",
  platform: "browser", // Workers runtime is browser-like, not Node
  minify: true,
  treeShaking: true,
  // Mark Node built-ins external so they don't polyfill into bundle
  external: ["node:crypto", "node:stream", "node:buffer"],
  // Replace dev-only branches at build time
  define: {
    "process.env.NODE_ENV": '"production"',
    __DEV__: "false",
  },
  // Enable package.json "exports" resolution for subpath imports
  conditions: ["workerd", "worker", "browser", "import", "default"],
  metafile: true,
  outfile: "dist/worker.mjs",
});
```

```toml
# wrangler.toml
[build]
command = "npx tsx build.ts"

[[rules]]
type = "ESModule"
globs = ["**/*.mjs"]
```

## Section 4 — Side-effect Annotation and Module Boundary Guards

Packages that lack `"sideEffects": false` in their `package.json` cannot be tree-shaken safely.
Patch them at the workspace level or use a custom plugin.

```typescript
// esbuild-no-side-effects-plugin.ts
import type { Plugin } from "esbuild";

// Packages verified to have no side effects despite missing annotation
const SAFE_PACKAGES = ["ms", "qs", "mime", "bytes", "on-finished"];

export const noSideEffectsPlugin: Plugin = {
  name: "no-side-effects",
  setup(build) {
    build.onResolve({ filter: /.*/ }, async (args) => {
      const result = await build.resolve(args.path, {
        resolveDir: args.resolveDir,
        kind: "import-statement",
      });
      const pkg = SAFE_PACKAGES.find((p) => args.path.startsWith(p));
      if (pkg) return { ...result, sideEffects: false };
      return result;
    });
  },
};

// Use in build.ts
await esbuild.build({
  // ...
  plugins: [noSideEffectsPlugin],
});
```

Verify with module-level guard pattern so Worker initialisation code never runs unused paths:

```typescript
// src/lib/analytics.ts
// Guard: only import heavy analytics when the route actually needs it
export async function getAnalyticsClient() {
  const { AnalyticsEngineClient } = await import("./analytics-engine-client.js");
  return new AnalyticsEngineClient();
}
```

## Anti-patterns

- Importing entire lodash/underscore: use `lodash-es` with subpath imports or native equivalents
- Mixing `require()` and `import` in the same module — CJS calls defeat ESM tree-shaking
- Re-exporting everything from an `index.ts` barrel inside your own codebase
- Using `import * as Lib from "lib"` when only one export is needed
- Ignoring `"sideEffects"` in workspace `package.json` — set it to `false` for your own packages
- Bundling polyfills (`buffer`, `crypto`, `stream`) — Workers provides these natively

## Gotchas

- `conditions: ["workerd"]` is required for packages that ship a special Workers build; without
  it you may accidentally bundle the Node.js variant (which is larger and may use unsupported APIs)
- `esbuild` does NOT tree-shake JSON imports beyond the root level; import only the keys you need
  via destructuring with an object spread from a `.ts` constant instead
- Wrangler v3+ automatically sets `--minify` in production builds but NOT `--tree-shaking`
  explicitly — the flag defaults to `true` for ESM but must be forced for mixed graphs
- The 1 MB *compressed* limit (gzip) is separate from the uncompressed parse limit; a 3 MB raw
  bundle can still deploy if it compresses under 1 MB, but parse time will be high

## Verification

```bash
# Check compressed size (must be < 1 MB)
npx wrangler deploy --dry-run --outdir dist
gzip -c dist/*.js | wc -c

# Confirm tree-shaking worked — dead symbol must be absent
grep -c "unusedFunction" dist/*.js  # should return 0

# Workers startup latency — measure cold isolate parse via tail log
npx wrangler tail --format=json | jq '.exceptions, .logs'
```

Compare `cf.executionModel` `{ cpuTime }` in the tail event before and after; a 30%+ bundle
reduction typically yields 2–5 ms faster cold starts.

## Related

- `/documentation/categories/performance/dead-code-elimination.md`
- `/documentation/categories/performance/javascript-tree-shaking-dead-code-elimination.md`
- `/documentation/categories/performance/workers-module-initialization-lazy-loading.md`
- `/documentation/categories/performance/workers-cold-start-optimization.md`
- `/documentation/categories/performance/pages-functions-bundle-size-optimization.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/bundling/
- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://esbuild.github.io/api/#tree-shaking
- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- https://community.cloudflare.com/t/workers-bundle-size-best-practices/
