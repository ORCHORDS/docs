# esbuild Define and Inject for Environment Variable Substitution in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your Cloudflare Worker references constants like `API_VERSION`, `RELEASE_SHA`, or
`BUILD_ENV` that should be baked into the bundle at build time — not read from
`wrangler.toml` vars at runtime. Using `process.env.X` fails silently in Workers
(the global is undefined), and putting secrets in `wrangler.toml` [vars] exposes them
in plaintext in the deployed Worker's settings. You want esbuild's `define` and `inject`
to substitute constants at compile time, zero-cost and tree-shake-friendly.

## Context

esbuild provides two orthogonal mechanisms for build-time code injection:

- **`define`** — replaces a bare identifier or `process.env.X` expression with a literal
  JSON value (string, number, boolean, JSON object). The replacement happens before
  parsing; dead branches are eliminated by the tree shaker.
- **`inject`** — prepends an import of a local module to every entry point, making its
  exports available as globals without an explicit import. Used for polyfilling Node APIs
  or providing a `process` shim.

Wrangler delegates bundling to esbuild and exposes both mechanisms. The same options are
available when using esbuild's JavaScript API directly (e.g., in a custom build script
or a Turborepo pipeline task).

Stack: Wrangler 3.x, esbuild 0.25+, TypeScript, pnpm, Turborepo.

## Using `define` via Wrangler Configuration

`wrangler.toml` supports `define` as a top-level table:

```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-10-01"

[define]
"process.env.NODE_ENV"     = '"production"'
"RELEASE_SHA"              = '"${COMMIT_SHA}"'   # NOT interpolated — set via env var
"API_VERSION"              = '"v2"'
"__DEV__"                  = 'false'
```

Because Wrangler does not interpolate shell variables in `wrangler.toml`, pass dynamic
values through the `--define` CLI flag:

```bash
wrangler deploy \
  --define "RELEASE_SHA:\"$(git rev-parse --short HEAD)\"" \
  --define "BUILD_TIMESTAMP:\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\""
```

In TypeScript, declare the constants as ambient globals so the compiler does not error:

```typescript
// src/env.d.ts
declare const RELEASE_SHA: string;
declare const BUILD_TIMESTAMP: string;
declare const API_VERSION: string;
declare const __DEV__: boolean;
```

Usage in the worker:

```typescript
// src/index.ts
export default {
  async fetch(request: Request): Promise<Response> {
    if (__DEV__) {
      console.log("dev mode — verbose logging enabled");
    }
    return Response.json({
      version: API_VERSION,
      sha: RELEASE_SHA,
      built: BUILD_TIMESTAMP,
    });
  },
} satisfies ExportedHandler;
```

After bundling, `__DEV__` is `false` (a literal), so the `if` branch is dead code and
esbuild eliminates it entirely. The bundle contains no reference to `console.log`.

## Using esbuild's JavaScript API Directly

When Wrangler's `define` table is insufficient (e.g., you need conditional defines per
environment, or you are running esbuild in a custom Turborepo pipeline task):

```typescript
// scripts/build.ts
import * as esbuild from "esbuild";
import { execSync } from "node:child_process";

const sha = execSync("git rev-parse --short HEAD").toString().trim();
const env = process.env.CF_ENV ?? "production";

const isDev = env === "development";

await esbuild.build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  outfile: "dist/worker.js",
  format: "esm",
  platform: "browser",   // Workers target; avoids Node built-in shims
  target: "es2022",
  define: {
    "process.env.NODE_ENV": JSON.stringify(env),
    RELEASE_SHA: JSON.stringify(sha),
    "__DEV__": String(isDev),
    "API_BASE_URL": JSON.stringify(
      isDev
        ? "http://localhost:8787"
        : "https://api.example.com"
    ),
  },
  // Ensure Workers-specific globals are not accidentally polyfilled
  conditions: ["workerd", "worker", "browser"],
});
```

Run via pnpm:

```bash
pnpm tsx scripts/build.ts
```

## Using `inject` to Shim process.env

If third-party packages reference `process.env` and you cannot patch them, provide a
shim via `inject` rather than individual `define` entries:

```typescript
// src/shims/process-env.ts
// This file is injected into every entry point.
// It must only export/assign globals — no side effects.
export const process = {
  env: {
    NODE_ENV: "production",
  },
};
```

In your build script:

```typescript
await esbuild.build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  format: "esm",
  platform: "browser",
  inject: ["src/shims/process-env.ts"],
  // No need for individual `define` entries for process.env.NODE_ENV —
  // the injected shim handles the entire process.env object.
});
```

With Wrangler, use the `inject` array in `wrangler.toml`:

```toml
[build]
command = ""    # Wrangler handles the build

# wrangler.toml does not expose `inject` directly; use a custom build command:
[build]
command = "pnpm tsx scripts/build.ts"
```

## Environment-Specific Define Sets in Turborepo

Define a reusable helper in `packages/build-config/src/defines.ts`:

```typescript
export function makeDefines(env: "development" | "staging" | "production"): Record<string, string> {
  const sha = process.env.COMMIT_SHA ?? "local";
  return {
    "__DEV__": String(env === "development"),
    "__STAGING__": String(env === "staging"),
    "RELEASE_SHA": JSON.stringify(sha),
    "process.env.NODE_ENV": JSON.stringify(
      env === "development" ? "development" : "production"
    ),
    "API_BASE_URL": JSON.stringify({
      development: "http://localhost:8787",
      staging: "https://staging.api.example.com",
      production: "https://api.example.com",
    }[env]),
  };
}
```

Consume it in each app's build script:

```typescript
import { makeDefines } from "@example-org/example-repo/defines";

const env = (process.env.CF_ENV ?? "production") as "development" | "staging" | "production";

await esbuild.build({
  entryPoints: ["src/index.ts"],
  bundle: true,
  format: "esm",
  platform: "browser",
  define: makeDefines(env),
});
```

## Verifying Substitution in the Bundle

```bash
# After building, grep the output for any un-substituted references
grep -E "process\.env|__DEV__|RELEASE_SHA" dist/worker.js && echo "LEAK DETECTED" || echo "clean"

# Inspect what esbuild actually emitted
cat dist/worker.js | head -50
```

Check bundle size impact — define-substituted dead branches should be absent:

```bash
# With __DEV__ = false, the dev-only branch should not appear
grep -c "verbose logging enabled" dist/worker.js
# Expected: 0
```

## Anti-patterns

- **Using `wrangler.toml` [vars] for build-time constants** — `[vars]` injects runtime
  environment variables readable via `env.X`. They are visible in the Cloudflare
  dashboard as plaintext. Use `[define]` for build-time constants and `wrangler secret`
  for sensitive runtime values.
- **Quoting mistakes in define values** — `define` values must be valid JSON expressions.
  `"production"` (without inner quotes) is a bare identifier, not a string literal.
  Always wrap strings: `'"production"'` in TOML, or `JSON.stringify("production")` in JS.
- **Injecting large modules** — `inject` prepends the shim to every entry point and it is
  included in the bundle even if unused. Keep shim files minimal; only define what is
  needed.
- **Defining `globalThis.X` directly in `wrangler.toml`** — Workers already expose
  Cloudflare globals on `globalThis`. Shadowing them with `define` causes confusing
  runtime vs. compile-time mismatches.

## Gotchas

- esbuild's `define` replaces the exact textual expression. `process.env["NODE_ENV"]`
  (bracket notation) is NOT replaced by `define: { "process.env.NODE_ENV": ... }`. Use
  dot notation in source code, or define `process.env` as a full object via `inject`.
- Wrangler's `--define` CLI flag uses `:` as the separator (`KEY:VALUE`), while
  esbuild's JS API uses an object. The value must still be a valid JSON expression on
  both sides.
- TypeScript's `declare const` only suppresses type errors; it does not guarantee
  esbuild actually replaces the identifier. If you forget to add the `define` entry,
  the identifier resolves to `undefined` at runtime with no compile-time error.
- When running tests with vitest-pool-workers, `define` substitutions from `wrangler.toml`
  are applied. If a test environment requires `__DEV__ = true`, override via
  `vitest.config.ts` `define` option, not via `wrangler.toml`.

## Verification

```bash
# Build production bundle
pnpm tsx scripts/build.ts

# Confirm RELEASE_SHA is baked in
grep "RELEASE_SHA" dist/worker.js   # should show the actual SHA value, not the identifier

# Deploy and verify the /version endpoint
wrangler deploy
curl https://my-worker.example.workers.dev/version
# {"version":"v2","sha":"abc1234","built":"2026-08-23T03:00:00Z"}
```

Run type-check to confirm ambient declarations cover all injected constants:

```bash
pnpm tsc --noEmit
```

## Related

- `esbuild-workers-plugins-custom-transforms.md`
- `esbuild-external-packages-workers-bundle.md`
- `esbuild-metafile-bundle-analysis-workers.md`
- `typescript-cloudflare-workers-strict.md`
- `wrangler-config-validation-ci.md`

## Sources

- esbuild define docs: https://esbuild.github.io/api/#define
- esbuild inject docs: https://esbuild.github.io/api/#inject
- Wrangler define config: https://developers.cloudflare.com/workers/wrangler/configuration/#define
- Workers runtime globals: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
