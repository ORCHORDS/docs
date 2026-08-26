# esbuild Workers Plugins and Custom Transforms

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Wrangler's default esbuild pipeline handles most Workers bundles, but projects that embed SQL migration files as strings, inline WASM modules, or replace environment-specific constants at build time need custom esbuild plugins. Writing plugins that run inside Wrangler's build step keeps the development workflow (`wrangler dev` hot-reload) and production build (`wrangler deploy`) consistent.

## Context

Wrangler exposes an `esbuild` key in `wrangler.toml` for basic flags, but for plugin-level control you need a custom build script that calls the esbuild JavaScript API directly and outputs to the format Wrangler expects (a single `esm` bundle entry). This script can then be invoked from `wrangler deploy --no-bundle --outdir dist` after the esbuild step produces `dist/index.js`.

## esbuild Plugin: Inline SQL Migrations

```typescript
// build-plugins/sql-loader.ts
import type { Plugin } from "esbuild";
import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";

/**
 * Imports *.sql files as typed string exports.
 * Usage: import schema from "./schema.sql";
 */
export function sqlLoaderPlugin(): Plugin {
  return {
    name: "sql-loader",
    setup(build) {
      build.onLoad({ filter: /\.sql$/ }, (args) => {
        const sql = readFileSync(args.path, "utf-8");
        return {
          contents: `export default ${JSON.stringify(sql)};`,
          loader: "js",
        };
      });

      // Resolve directory imports: import migrations from "./migrations/"
      build.onResolve({ filter: /\/$/ }, (args) => {
        if (args.kind !== "import-statement") return;
        const dir = resolve(args.resolveDir, args.path);
        return { path: dir, namespace: "sql-dir" };
      });

      build.onLoad({ filter: /.*/, namespace: "sql-dir" }, (args) => {
        const files = readdirSync(args.path)
          .filter((f) => f.endsWith(".sql"))
          .sort(); // alphabetical = version order

        const entries = files.map((f) => {
          const content = readFileSync(join(args.path, f), "utf-8");
          const key = f.replace(/\.sql$/, "");
          return `  ${JSON.stringify(key)}: ${JSON.stringify(content)}`;
        });

        return {
          contents: `export default {\n${entries.join(",\n")}\n};`,
          loader: "js",
        };
      });
    },
  };
}
```

## esbuild Plugin: Compile-time Constant Replacement

```typescript
// build-plugins/define-env.ts
import type { Plugin } from "esbuild";

interface ConstantMap {
 | number | boolean;
}

/**
 * Replaces __BUILD_*__ placeholders with literal values baked into the bundle.
 * Avoids shipping Wrangler secrets that should instead stay in env vars at runtime.
 */
export function defineEnvPlugin(constants: ConstantMap): Plugin {
  const define: Record<string, string> = {};
  for (const [k, v] of Object.entries(constants)) {
    define[`__BUILD_${k}__`] = JSON.stringify(v);
  }

  return {
    name: "define-env",
    setup(build) {
      // Merge into esbuild's own define map
      build.initialOptions.define = {
        ...build.initialOptions.define,
        ...define,
      };
    },
  };
}
```

## Custom Build Script

```typescript
// scripts/build.ts — run before wrangler deploy --no-bundle
import * as esbuild from "esbuild";
import { sqlLoaderPlugin } from "../build-plugins/sql-loader";
import { defineEnvPlugin } from "../build-plugins/define-env";

const isProd = process.env.NODE_ENV === "production";

await esbuild.build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  format: "esm",
  target: "es2022",
  outfile: "dist/index.js",
  // Workers require a single output file; splitting is unsupported at runtime
  splitting: false,
  minify: isProd,
  sourcemap: isProd ? "external" : "inline",
  // Workers do not have Node.js built-ins by default
  platform: "browser",
  conditions: ["workerd", "worker", "browser"],
  plugins: [
    sqlLoaderPlugin(),
    defineEnvPlugin({
      COMMIT_SHA: process.env.CF_PAGES_COMMIT_SHA ?? "local",
      BUILD_TIME: Date.now(),
    }),
  ],
  // Surface bundle size in CI logs
  metafile: true,
});

// Print top contributors to bundle size
const meta = await esbuild.analyzeMetafile("dist/meta.json");
console.log(meta);
```

## wrangler.toml for No-bundle Deploys

```toml
name = "my-worker"
main = "dist/index.js"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]

# Tell wrangler the bundle is pre-built — skip its own esbuild pass
[build]
command = "pnpm tsx scripts/build.ts"
```

## Anti-patterns

- Using `loader: "text"` on `.sql` files via `wrangler.toml`'s `rules` key and then also running a plugin — the two pipelines conflict, causing the file to be processed twice.
- Setting `platform: "node"` in the esbuild config for a Worker bundle; this injects Node.js polyfills that inflate the bundle and may exceed the 10 MB compressed Workers limit.
- Writing plugins that perform network requests (e.g., fetching a remote schema) at build time; this breaks offline development and makes builds non-deterministic.

## Gotchas

- esbuild plugins run in Node.js during the build step, but the *output* must be valid for the `workerd` runtime. Avoid importing Node-only modules inside plugin-generated code strings.
- When using `--no-bundle` with Wrangler, `wrangler dev` still runs its own internal esbuild; you must also pass `--no-bundle` to `wrangler dev` or maintain a separate dev build step to keep plugin behaviour consistent.
- The `conditions` array must include `"workerd"` so packages that ship separate Workers-compatible exports (e.g., `hono`) resolve the correct entry points.

## Verification

```bash
# Build and inspect metafile
pnpm tsx scripts/build.ts
cat dist/meta.json | pnpm esbuild --analyze

# Check bundle size against Workers 10 MB limit
wc -c dist/index.js

# Deploy with pre-built bundle
wrangler deploy --no-bundle

# Confirm SQL string is inlined
grep -c "CREATE TABLE" dist/index.js
```

## Related

- `devtools/wrangler-dev-local-d1-r2-kv.md`
- `devtools/vite-cloudflare-workers-dev-mode.md`
- `devtools/bundle-size-tracking-size-limit-ci.md`

## Sources

- https://esbuild.github.io/plugins/
- https://developers.cloudflare.com/workers/wrangler/bundling/
- https://developers.cloudflare.com/workers/platform/limits/#worker-size
