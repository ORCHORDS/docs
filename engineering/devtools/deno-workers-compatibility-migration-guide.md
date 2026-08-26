# Deno Workers Compatibility Migration Guide

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Some example project shared utility packages were originally written for Deno (using `Deno.env`, `Deno.serve`, `Deno.readTextFile`, and top-level `URL` construction with `import.meta.url`). Migrating these utilities to run on Cloudflare Workers without a full rewrite requires understanding which APIs overlap, which need polyfills, and which must be replaced entirely.

## Context

Deno and Cloudflare Workers both implement the WinterCG (Web-interoperable Runtimes Community Group) subset of the Web Platform APIs, making them more compatible than Node.js and Workers. However, Deno adds a `Deno.*` namespace for OS-level access that does not exist in Workers, and Workers adds Cloudflare-specific bindings (`env.KV`, `env.D1`, `SELF`) that Deno does not model. A structured migration identifies the compatibility surface before touching code.

## Compatibility Audit

Run a static grep across the package to find Deno-specific usage before migrating:

```bash
# Find all Deno namespace usages
grep -rn "Deno\." packages/shared-utils/src/ | sort -u

# Find Node compat imports that won't work in Workers
grep -rn "node:" packages/shared-utils/src/ | sort -u

# Find import.meta.url used for file resolution (unsupported in Workers)
grep -rn "import\.meta\.url" packages/shared-utils/src/ | sort -u
```

Common Deno APIs and their Workers equivalents:

| Deno API | Workers Equivalent |
|---|---|
| `Deno.env.get("KEY")` | `env.KEY` (binding) or `globalThis.KEY` |
| `Deno.serve(handler)` | `export default { fetch }` |
| `Deno.readTextFile(path)` | No direct equivalent — use R2 or KV |
| `Deno.exit(1)` | Not applicable — throw instead |
| `Deno.openKv()` | `env.KV` (Cloudflare KV binding) |
| `Deno.cron()` | Cloudflare Cron Triggers |
| `new URL(path, import.meta.url)` | Bundle the file or use a virtual module |

## Migrating Environment Variable Access

Deno utilities often read env vars via `Deno.env.get`. Workers receives env as the second argument to `fetch`. The cleanest migration passes env through explicitly rather than reaching for a global.

```typescript
// Before (Deno)
export function getJwtSecret(): string {
  const secret = <redacted-secret>"JWT_SECRET");
  if (!secret) throw new Error("JWT_SECRET not set");
  return secret;
}

// After (Workers — env-injected pattern)
export interface JwtSecretEnv {
  JWT_SECRET: string;
}

export function getJwtSecret(env: JwtSecretEnv): string {
  if (!env.JWT_SECRET) throw new Error("JWT_SECRET not set");
  return env.JWT_SECRET;
}
```

For utilities used across many functions, create a typed env accessor:

```typescript
// src/lib/env.ts
export type WorkersEnv = {
  JWT_SECRET: string;
  ANONYMOUS_SALT: string;
  KV: KVNamespace;
  DB: D1Database;
};

// Thread env through a context object to avoid globals
export interface AppContext {
  env: WorkersEnv;
  request: Request;
}
```

## Migrating Deno.serve to Workers Fetch Handler

```typescript
// Before (Deno)
import { router } from "./router.ts";

Deno.serve({ port: 8000 }, router);

// After (Workers)
import { router } from "./router";

export default {
  async fetch(request: Request, env: WorkersEnv, ctx: ExecutionContext): Promise<Response> {
    return router(request, env, ctx);
  },
} satisfies ExportedHandler<WorkersEnv>;
```

If the original Deno code uses `Deno.serve`'s `onListen` callback for readiness, remove it — Workers has no concept of a server lifecycle; the Worker is "ready" as soon as the module is evaluated.

## Migrating File I/O

Workers has no filesystem. Deno utilities that read configuration files (e.g., `Deno.readTextFile("./config.json")`) must move that data to one of:

- **Bundled at build time** via a Vite virtual module (see `vite-workers-build-plugin-custom.md`)
- **KV namespace** for mutable configuration that changes without a redeploy
- **R2 object** for large binary blobs or assets

```typescript
// Before (Deno)
const config = JSON.parse(await Deno.readTextFile("./config/routes.json"));

// After (Workers — KV)
export async function loadRoutesConfig(kv: KVNamespace): Promise<RoutesConfig> {
  const raw = await kv.get("config:routes", { type: "json" });
  if (!raw) throw new Error("routes config not found in KV");
  return raw as RoutesConfig;
}

// After (Workers — bundled)
// In vite.config.ts, virtualise the file:
// import config from "virtual:routes-config";
```

## Compatibility Flags and Node.js Built-ins

Some Deno packages use npm specifiers (`npm:zod`, `npm:hono`) that translate directly to Workers with no changes. Other Deno packages use the `node:` protocol. Enable Node.js compatibility in `wrangler.toml`:

```toml
compatibility_date = "2025-01-01"
compatibility_flags = ["nodejs_compat"]
```

Then verify each `node:` import against the Workers Node.js compat matrix:

```typescript
// These work with nodejs_compat:
import { Buffer } from "node:buffer";
import { createHash } from "node:crypto";
import { EventEmitter } from "node:events";

// These do NOT work in Workers even with nodejs_compat:
// import { readFileSync } from "node:fs";   // no filesystem
// import { createServer } from "node:http"; // no TCP server
// import { Worker } from "node:worker_threads"; // no threads
```

## Anti-patterns

- Wrapping `Deno.*` calls in try/catch to silently swallow errors in Workers — `Deno` is not defined in the Workers global scope and will throw a `ReferenceError` synchronously
- Using `globalThis.Deno` as a feature-detect and falling back to Workers APIs in the same file — this creates unmaintainable dual-runtime code; split into separate modules instead
- Importing Deno's standard library (`https://deno.land/std/...`) — URL imports are not supported in Workers; pin to npm equivalents
- Assuming `crypto.randomUUID()` behaves identically — both Deno and Workers implement it, but Deno's `crypto.getRandomValues()` buffer size limit is 65536 bytes; Workers matches the Web Crypto spec without this limit

## Gotchas

- Deno's `import.meta.resolve()` resolves to `file://` URLs; Workers has no equivalent and the resolved path would be meaningless in the bundle
- Deno modules use `.ts` extensions in import paths; Workers (via esbuild/Vite) does not require extensions — remove them or configure the bundler's `resolve.extensions`
- `Deno.openKv()` returns a strongly typed transactional KV with watches; Cloudflare KV has eventual consistency and no transactions — rewrite any code that depends on `kv.watch()` using Durable Objects instead
- Top-level `await` is supported in both runtimes but Workers evaluates the module fresh per isolate instantiation; expensive top-level awaits (e.g., reading a config from KV) add cold-start latency

## Verification

```bash
# After migration, build the package targeting Workers
wrangler deploy --dry-run --outdir dist/

# Check for any remaining Deno references in the bundle
grep -c "Deno\." dist/worker.js && echo "Deno refs remain — check migration"

# Run unit tests in Vitest Workers pool (not Deno test)
pnpm vitest run --project workers

# Verify types with the Workers type definitions
npx tsc --noEmit --project tsconfig.workers.json
```

## Related

- `bun-workers-compatibility-testing.md`
- `wrangler-dev-local-d1-r2-kv.md`
- `typescript-cloudflare-workers-strict.md`
- `vite-workers-build-plugin-custom.md`
- `miniflare-v4-migration-guide.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- https://wintercg.org/
- https://deno.com/blog/deno-on-cloudflare
- https://developers.cloudflare.com/workers/wrangler/compatibility-dates/
- https://docs.deno.com/runtime/reference/migrate_deprecations/
