# esbuild Platform, Polyfill, and Node Compatibility for Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

An npm package that works fine in Node CI fails at runtime inside a Cloudflare Worker with errors like `process is not defined`, `Buffer is not defined`, or `__dirname is not defined`. Alternatively, you ship a Worker bundle that accidentally includes full Node.js polyfills for `crypto`, `stream`, and `path`, ballooning the bundle from 50 KB to 800 KB. You need precise control over what esbuild shims versus what the Workers runtime provides natively.

---

## Context

esbuild's `--platform` flag changes the default set of built-in assumptions and which globals/modules are considered external. The three values — `browser`, `node`, and `neutral` — behave very differently, and the Workers runtime matches none of them exactly:

- Workers is **not** a browser: no `window`, no `document`, no `localStorage`.
- Workers is **not** Node: no `fs`, no `process.env`, no `require()` at runtime.
- Workers has its own `crypto` (WebCrypto), its own `fetch`, its own `TextEncoder`.
- With `nodejs_compat` compatibility flag, Workers exposes a curated subset of Node builtins natively.

Wrangler wraps esbuild with opinionated defaults, but understanding the underlying flags helps when you call esbuild directly (custom build scripts, library authors, monorepo tooling).

Stack:

- `esbuild` ^0.21
- `wrangler` ^4.0
- `@esbuild-plugins/node-globals-polyfill` ^0.2 (optional)

---

## Platform Flag Behavior

```ts
// build.ts
import * as esbuild from "esbuild";

await esbuild.build({
  entryPoints: ["src/worker.ts"],
  bundle: true,
  outfile: "dist/worker.js",
  format: "esm",

  // ✅ Correct baseline for Workers
  platform: "browser",

  // Workers globals that esbuild must NOT replace/polyfill
  // (they exist natively in the runtime)
  inject: [],       // no Node globals inject by default
  define: {
    // Workers has no process.env; eliminate it at build time
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
});
```

Why `platform: "browser"`:
- Marks Node built-ins (`fs`, `path`, `os`, etc.) as **unavailable** — esbuild errors at bundle time rather than silently including stubs.
- Does **not** inject `process`, `Buffer`, or `__dirname` shims (those are Node-only shims added by `platform: "node"`).
- Sets `mainFields: ["browser", "module", "main"]` so packages with browser-specific entry points are resolved correctly.

---

## Handling node_modules That Use process / Buffer

When a third-party package references `process.env` or `Buffer`, use targeted defines/injects rather than pulling in the entire `node-polyfill` plugin:

```ts
import { NodeGlobalsPolyfillPlugin } from "@esbuild-plugins/node-globals-polyfill";

await esbuild.build({
  entryPoints: ["src/worker.ts"],
  bundle: true,
  outfile: "dist/worker.js",
  format: "esm",
  platform: "browser",
  plugins: [
    NodeGlobalsPolyfillPlugin({
      // Inject only what you actually need
      process: true,
      buffer: true,
    }),
  ],
  define: {
    // Keep NODE_ENV as a literal so dead-code elimination works
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
});
```

This injects a ~2 KB `process` shim and the `Buffer` polyfill from the `buffer` npm package, rather than the full 200 KB `node-stdlib-browser` bundle.

---

## nodejs_compat: Let the Runtime Handle It

With `compatibility_flags = ["nodejs_compat"]` in `wrangler.toml`, the Workers runtime natively provides:

- `node:crypto` → WebCrypto-backed implementation
- `node:buffer` → native `Buffer`
- `node:stream`, `node:events`, `node:util`, `node:path`, `node:url`, and more

When building with Wrangler, these are automatically marked as external so esbuild does not bundle them:

```toml
# wrangler.toml
compatibility_date = "2024-09-23"
compatibility_flags = ["nodejs_compat"]
```

```ts
// In a custom esbuild script — mirror what Wrangler does
await esbuild.build({
  entryPoints: ["src/worker.ts"],
  bundle: true,
  outfile: "dist/worker.js",
  format: "esm",
  platform: "browser",
  // Mark node: built-ins as external — the Workers runtime provides them
  external: [
    "node:crypto",
    "node:buffer",
    "node:stream",
    "node:stream/web",
    "node:events",
    "node:util",
    "node:path",
    "node:url",
    "node:os",
    "node:http",
    "node:https",
    "node:net",
    "node:tls",
    "node:zlib",
    "node:assert",
    "node:fs",
    "node:fs/promises",
    "node:child_process",
    "node:worker_threads",
  ],
});
```

Without marking these external, esbuild may resolve them to empty stubs or the npm `node-stdlib-browser` shims, which are orders of magnitude larger than the native runtime equivalents.

---

## Checking What Ends Up in the Bundle

Use esbuild's metafile to catch accidental polyfill bloat:

```ts
const result = await esbuild.build({
  entryPoints: ["src/worker.ts"],
  bundle: true,
  outfile: "dist/worker.js",
  format: "esm",
  platform: "browser",
  metafile: true,
});

// Write metafile for analysis
await Bun.write("dist/meta.json", JSON.stringify(result.metafile));
```

```bash
# Inspect with esbuild's online analyzer or locally
npx esbuild --analyze dist/meta.json

# Or pipe to jq to find large inputs
cat dist/meta.json | jq '
  .inputs
  | to_entries
  | sort_by(-.value.bytes)
  | .[0:10]
  | .[]
  | {file: .key, kb: (.value.bytes / 1024 | floor)}
'
```

If you see `node_modules/readable-stream` or `node_modules/buffer` in the top-10, you likely have an accidental polyfill inclusion. Switch to `nodejs_compat` externals instead.

---

## Anti-patterns

- **`platform: "node"` for a Workers bundle**: This tells esbuild that Node built-ins are available at runtime and sets `mainFields: ["main"]`, bypassing browser-specific package entries. The resulting bundle assumes a Node environment that does not exist.
- **`platform: "neutral"` without explicit `mainFields`**: Neutral disables all platform assumptions, including `mainFields`. You must set `mainFields: ["browser", "module", "main"]` manually or package resolution silently falls back to CJS `main` entries, missing browser-optimized code.
- **Bundling `node:crypto` without `nodejs_compat`**: The polyfill works in Miniflare locally but fails in production because the Workers runtime without `nodejs_compat` does not expose `node:` imports at runtime. Always match your `compatibility_flags` in `wrangler.toml` to what you `external` in esbuild.
- **Relying on esbuild's `--inject` for `__dirname`**: `__dirname` is a CommonJS concept. If your dependency uses it, prefer a package that ships an ESM build, or `define: { __dirname: JSON.stringify("/") }` as a last resort.

---

## Gotchas

- `platform: "browser"` sets `conditions: ["browser", "import", "default"]` for package exports resolution. Some packages ship a `"worker"` condition (e.g., `@sentry/cloudflare`); you must add `"worker"` to `conditions` manually.
- Wrangler's internal esbuild invocation adds `--conditions=workerd` for the Workers-specific condition. If you call esbuild directly, replicate this: `conditions: ["workerd", "worker", "browser", "import", "default"]`.
- The `process.env` shim injected by `NodeGlobalsPolyfillPlugin` is an empty object `{}` at runtime. Code that reads `process.env.MY_SECRET` at runtime (not compile time) will get `undefined`. Secrets must come from `env.MY_SECRET` bindings, not `process.env`.
- `Buffer.from()` from the polyfill and `Buffer.from()` from `node:buffer` (with `nodejs_compat`) are different objects. Libraries that do `instanceof Buffer` checks across module boundaries may fail.

---

## Verification

```bash
# Build and check output size
pnpm build
ls -lh dist/worker.js

# Confirm no accidental Node polyfill in bundle
grep -c "readable-stream\|node-stdlib-browser\|process-es6" dist/worker.js || echo "clean"

# Deploy to preview and confirm no runtime errors
wrangler deploy --env preview
wrangler tail --env preview
```

---

## Related

- `esbuild-external-packages-workers-bundle.md`
- `esbuild-metafile-bundle-analysis-workers.md`
- `esbuild-workers-plugins-custom-transforms.md`
- `vite-cloudflare-workers-dev-mode.md`
- `wrangler-config-validation-ci.md`
- `bundle-size-tracking-size-limit-ci.md`

---

## Sources

- esbuild platform docs: https://esbuild.github.io/api/#platform
- esbuild conditions: https://esbuild.github.io/api/#conditions
- Cloudflare Workers `nodejs_compat`: https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- `@esbuild-plugins/node-globals-polyfill`: https://github.com/nicolo-ribaudo/esbuild-plugin-node-globals-polyfill
- Workers compatibility flags: https://developers.cloudflare.com/workers/configuration/compatibility-dates/
