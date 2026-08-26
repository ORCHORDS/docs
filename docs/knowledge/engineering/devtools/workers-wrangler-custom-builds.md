# Custom Build Pipeline Configuration with Wrangler

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker project requires a preprocessing step before Wrangler bundles the final output — transpiling a non-standard language, generating code from a schema, inlining assets, or running a custom esbuild plugin that Wrangler's built-in bundler does not expose. You want deterministic builds locally and in CI without maintaining a parallel build system.

## Context

Wrangler v3+ exposes a `[build]` section in `wrangler.toml` that lets you delegate the bundling step entirely to your own toolchain. When `[build]` is configured, Wrangler calls your command, waits for it to produce a single `.js` file at `main`, and then uploads the result without re-bundling. This is distinct from the default path where Wrangler calls esbuild internally.

Key facts:
- `[build].command` runs in the repo root via the system shell.
- `[build].watch_dir` (array or string) tells `wrangler dev` which directories trigger a rebuild on change.
- The output file referenced by the top-level `main` field must exist after `command` finishes.
- Wrangler still handles uploading source maps, secrets injection, and compatibility flags; only *bundling* is delegated.
- `[env.<name>]` blocks can each carry their own `[build]` overrides.

## Solution

```typescript
// build.ts  — custom esbuild driver invoked by Wrangler's [build] command
import * as esbuild from 'esbuild';
import { wasmPlugin } from './plugins/wasm-plugin';
import { envInlinePlugin } from './plugins/env-inline-plugin';
import * as fs from 'node:fs';
import * as path from 'node:path';

const isCI = process.env.CI === 'true';
const isProd = process.env.NODE_ENV === 'production';

/** Resolve every entrypoint declared in wrangler.toml via an env var injected
 *  from a wrapper shell script, defaulting to src/index.ts for simple projects. */
const entryPoints: string[] = (process.env.WORKER_ENTRYPOINTS ?? 'src/index.ts')
  .split(',')                          // multi-entrypoint: "src/a.ts,src/b.ts"
  .map((p) => p.trim())
  .filter(Boolean);

const outdir = 'dist';

async function build(): Promise<void> {
  fs.mkdirSync(outdir, { recursive: true });

  const result = await esbuild.build({
    entryPoints,
    bundle: true,
    outdir,
    format: 'esm',
    target: 'es2022',
    platform: 'browser',   // Workers runtime — not Node
    conditions: ['workerd', 'worker', 'browser'],
    sourcemap: isProd ? 'external' : 'inline',
    minify: isProd,
    treeShaking: true,
    metafile: true,         // enables bundle-size analysis (see bundle-size article)
    logLevel: isCI ? 'warning' : 'info',
    define: {
      // Cloudflare Workers does not have process.env at runtime;
      // inline build-time constants here instead.
      'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV ?? 'development'),
      'BUILD_TIME': JSON.stringify(new Date().toISOString()),
    },
    plugins: [
      wasmPlugin(),          // converts .wasm imports → base64 inline module
      envInlinePlugin(),     // strips Node-only env-var reads
    ],
    // Prevent accidentally bundling packages that should be kept external.
    // Workers has no node_modules at runtime, so this list catches mistakes early.
    external: [],
  });

  if (result.metafile) {
    fs.writeFileSync(
      path.join(outdir, 'meta.json'),
      JSON.stringify(result.metafile),
    );
  }

  const text = await esbuild.analyzeMetafile(result.metafile!, { verbose: false });
  console.log(text);
}

build().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

```toml
# wrangler.toml
name        = "my-worker"
compat_date = "2024-09-23"
main        = "dist/index.js"   # must match esbuild outdir + entrypoint stem

[build]
command   = "node --import tsx/esm build.ts"
watch_dir = ["src", "plugins"]   # wrangler dev re-runs command when these change

[env.production]
[env.production.build]
command = "NODE_ENV=production node --import tsx/esm build.ts"

[env.staging]
[env.staging.build]
command = "NODE_ENV=staging node --import tsx/esm build.ts"
```

```typescript
// plugins/wasm-plugin.ts  — inline .wasm files as base64 data URLs
import type { Plugin } from 'esbuild';
import * as fs from 'node:fs';

export function wasmPlugin(): Plugin {
  return {
    name: 'wasm-inline',
    setup(build) {
      build.onResolve({ filter: /\.wasm$/ }, (args) => ({
        path: args.path,
        namespace: 'wasm-inline',
      }));

      build.onLoad({ filter: /.*/, namespace: 'wasm-inline' }, async (args) => {
        const bytes = fs.readFileSync(args.path);
        const b64 = bytes.toString('base64');
        return {
          // Export a WebAssembly.Module directly — Workers supports top-level await
          contents: `
            const wasmBytes = Uint8Array.from(atob("${b64}"), c => c.charCodeAt(0));
            export default new WebAssembly.Module(wasmBytes);
          `,
          loader: 'js',
        };
      });
    },
  };
}
```

```typescript
// plugins/env-inline-plugin.ts  — replace process.env.* with empty strings
// so tree-shaking removes Node-only code paths
import type { Plugin } from 'esbuild';

export function envInlinePlugin(): Plugin {
  return {
    name: 'env-inline',
    setup(build) {
      build.onEnd(() => {
        // Nothing to do at the plugin level — definitions in the top-level
        // `define` map already handle this.  Plugin kept as extension point.
      });
    },
  };
}
```

```jsonc
// package.json scripts
{
  "scripts": {
    "build":      "node --import tsx/esm build.ts",
    "build:prod": "NODE_ENV=production node --import tsx/esm build.ts",
    "dev":        "wrangler dev",
    "deploy":     "wrangler deploy --env production",
    "deploy:staging": "wrangler deploy --env staging"
  }
}
```

## Implementation Details

**Command execution context.** `[build].command` is passed to the system shell (`sh -c` on Linux/macOS, `cmd /c` on Windows). Environment variables present in the wrangler process are inherited, so `CI=true` set by your CI provider is visible inside the build script without extra plumbing.

**Multi-entrypoint builds.** Workers supports multiple entrypoints via `[wrangler.toml]`'s top-level `main` (single) or via Named Entrypoints (`[wrangler.toml]` `services` / `dispatch_namespaces`). When using a custom build you must produce one output file per entrypoint and reference each with the correct `main` or service binding path. The example above reads a comma-separated env var so the build script stays single-file.

**Environment-specific flags.** Override `[build].command` under `[env.<name>]` rather than branching inside the build script. This keeps CI pipelines clean: `wrangler deploy --env production` automatically picks up the production build command with `NODE_ENV=production`.

**`wrangler dev` watch loop.** With `watch_dir` set, Wrangler starts an `fs.watch` on those paths. On a change it kills the previous build process, re-runs `command`, and hot-reloads the Worker. Keep build times under ~2 s for a comfortable dev loop; use esbuild's incremental API if preprocessing steps are expensive.

**CI vs local builds.** In CI, always run `wrangler deploy` (not `wrangler dev`). The `[build].command` runs once and exits. Set `CI=true` in your pipeline (GitHub Actions does this automatically) so the build script can suppress interactive output and treat all warnings as errors (`logLevel: 'error'` in esbuild).

## Anti-patterns

- **Calling `wrangler deploy` from inside the build command.** The build command must only produce output files. Wrangler handles deployment after the command exits. Nesting calls creates a deadlock.
- **Referencing `node_modules` paths as `external` when they are needed at runtime.** Workers has no `node_modules` directory. Every dependency must be bundled.
- **Using `platform: 'node'` in esbuild.** This injects Node shims that bloat the bundle and may reference APIs unavailable in the Workers runtime. Always use `platform: 'browser'` with `conditions: ['workerd', 'worker', 'browser']`.
- **Forgetting `watch_dir` covers only the listed roots.** Files outside `watch_dir` that change will not trigger a rebuild in `wrangler dev`. Missing a directory causes stale builds that are hard to diagnose.

## Gotchas

- Wrangler reads `main` *after* the build command exits. If the file is missing, Wrangler exits with a confusing "no such file" error rather than a build error. Ensure your build script exits non-zero on failure.
- Source maps must be produced by the custom build script. Set `sourcemap: 'external'` in esbuild and enable `upload_source_maps = true` in `wrangler.toml`; Wrangler will pick up the adjacent `.js.map` file.
- `tsx` (`node --import tsx/esm`) adds ~150 ms startup overhead. For hot rebuilds in `wrangler dev`, prefer compiling `build.ts` to `build.js` once as a pre-step and running `node build.js` in the watch loop.
- The `[build]` section is not supported for Pages Functions. Use `functions/` directory conventions or a Pages-specific build plugin instead.

## Verification

```bash
# Local: confirm the build script runs and produces dist/index.js
node --import tsx/esm build.ts
ls -lh dist/

# Dry-run deploy (bundles + validates, does not publish)
wrangler deploy --dry-run --outdir .wrangler/output --env production

# Confirm watch_dir triggers rebuild
wrangler dev &
# In another terminal:
touch src/index.ts
# Wrangler should print "Reloading worker..."

# CI smoke test
CI=true NODE_ENV=production node --import tsx/esm build.ts && echo OK
```

## Related

- `documentation/docs/policies/devtools/workers-bundle-size-analysis.md` — analyzing the metafile produced by this build
- `documentation/docs/policies/devtools/workers-sourcemap-debugging.md` — uploading the source maps generated here
- Wrangler docs: [Custom builds](https://developers.cloudflare.com/workers/wrangler/configuration/#build)

## Sources

- https://developers.cloudflare.com/workers/wrangler/configuration/#build
- https://esbuild.github.io/plugins/
- https://esbuild.github.io/api/#metafile
- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
