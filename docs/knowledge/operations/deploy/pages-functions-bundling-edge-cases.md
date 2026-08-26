# Pages Functions Bundling Edge Cases

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Pages Functions build succeeds locally with `wrangler pages dev` but
fails during the Pages CI build with errors like `Cannot find module`, `Dynamic require
of "X" is not supported`, `Top-level await is not available in the configured target
environment`, or the deploy succeeds but the Function throws at runtime because a native
Node.js module (`crypto`, `fs`, `path`) is unavailable. You need to understand how
Pages Functions are bundled and how to work around the sharp edges.

## Context

Pages Functions are bundled with **esbuild** targeting the `workerd` runtime. The
bundler:
- Resolves imports relative to `functions/` at build time
- Runs in **ESM output mode** with no CommonJS wrapper
- Does not polyfill Node.js built-ins by default
- Does not support native addons (`.node` files)
- Has a per-Function **1 MB compressed size limit** (as of 2026)

The Pages CI build environment is controlled by Cloudflare; you cannot install arbitrary
build tools. All bundling happens via Wrangler's internal esbuild invocation.

---

## Edge Case 1 — CommonJS-Only npm Packages

Some packages ship only CommonJS (`require()`/`module.exports`) with no ESM entrypoint.
esbuild usually handles the interop, but packages that call `require()` **dynamically**
at runtime (e.g. `require(someVariable)`) cannot be statically bundled.

**Symptom**: `Dynamic require of "pg" is not supported`

**Fix**: Use an edge-compatible fork or a bundler-friendly alternative.

```typescript
// functions/api/db.ts — BROKEN: pg uses dynamic require internally
import { Pool } from "pg";  // ❌ will fail at runtime in workerd

// FIXED option 1: use Cloudflare D1 instead of pg
// FIXED option 2: use hyperdrive + pg with nodejs_compat
```

```toml
# wrangler.toml — enable nodejs_compat to unlock pg + hyperdrive
compatibility_flags = ["nodejs_compat"]

[[hyperdrive]]
binding    = "DB"
localConnectionString = "postgresql://user:pass@localhost:5432/dev"
id         = "hyperdrive-id"
```

```typescript
// functions/api/db.ts — with nodejs_compat + hyperdrive
import { Pool } from "pg";

export function getPool(hyperdrive: Hyperdrive): Pool {
  return new Pool({ connectionString: hyperdrive.connectionString });
}
```

---

## Edge Case 2 — Node.js Built-ins Without nodejs_compat

```typescript
// functions/utils/hash.ts — BROKEN
import { createHash } from "crypto";   // ❌ not available without flag

// FIXED: use the Web Crypto API (always available in workerd)
export async function sha256(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
```

When you **must** use the Node.js `crypto` module (e.g. a third-party dependency does),
enable the flag:

```toml
# wrangler.toml
compatibility_date  = "2024-09-23"
compatibility_flags = ["nodejs_compat"]
```

The flag makes `node:crypto`, `node:buffer`, `node:stream`, `node:path`, `node:util`,
`node:events`, `node:url`, and others available as built-in modules. Verify which ones
are supported: https://developers.cloudflare.com/workers/runtime-apis/nodejs/

---

## Edge Case 3 — Large Dependencies Exceeding the 1 MB Bundle Limit

**Symptom**: Pages build fails with `Error: Script too large.`

```bash
# Diagnose bundle size locally before deploying
npx wrangler pages dev --compatibility-flag nodejs_compat 2>&1 | grep -i "size\|bytes"

# Or run esbuild directly to inspect output size per function:
npx esbuild functions/api/[[path]].ts \
  --bundle \
  --platform=browser \
  --target=es2022 \
  --format=esm \
  --outfile=/tmp/fn-bundle.js \
  --analyze
du -sh /tmp/fn-bundle.js
```

**Fix strategies**:

```typescript
// functions/api/pdf.ts — BROKEN: pdfmake is 2+ MB
import pdfMake from "pdfmake/build/pdfmake";  // ❌ too large

// FIXED option A: move PDF generation to a separate Worker (Service Binding)
// FIXED option B: use a lighter alternative (pdfkit with tree-shaking)
// FIXED option C: generate PDF client-side and upload to R2

// If the heavy import is in a shared utility, split it:
// functions/
//   _shared/lightweight-util.ts   ← imported by many Functions
//   api/heavy-route.ts            ← imports large dep, stands alone
```

---

## Edge Case 4 — Top-Level Await

Pages Functions support top-level await only in **module-format** files (`.ts`/`.mjs`).
If your function file has a CommonJS-like structure, esbuild will reject top-level await.

```typescript
// functions/api/config.ts — BROKEN if treated as CJS
const config = await fetchRemoteConfig();   // ❌ top-level await in CJS context

// FIXED: ensure the file is treated as ESM; add explicit import/export
import type { Env } from "../types";

const config = await fetchRemoteConfig();   // ✅ works in ESM module context

export const onRequest: PagesFunction<Env> = async (ctx) => {
  return Response.json(config);
};
```

---

## Edge Case 5 — External Modules Marked as External by esbuild

By default, Wrangler bundles everything. If you use `--no-bundle` (rarely needed), or
your `package.json` has `"type": "module"` but the dependency resolves to a CJS file,
esbuild may mark the module as external, producing a runtime error.

```toml
# wrangler.toml — force bundling of everything (default, but explicit)
[build]
command = "npm run build"

# Do NOT use --no-bundle in Pages Functions; it is not supported
```

Inspect which modules esbuild is externalising:

```bash
CLOUDFLARE_API_TOKEN=dummy npx wrangler pages deploy dist \
  --project-name test --dry-run 2>&1 | grep -i "external\|warn"
```

---

## Edge Case 6 — Monorepo Shared Packages

When `functions/` imports from a workspace package (e.g. `@acme/shared`) the Pages CI
build must be able to resolve that package.

```json
// package.json at repo root
{
  "workspaces": ["packages/*", "apps/*"]
}
```

```toml
# wrangler.toml
[build]
command = "npm run build --workspace=apps/my-app"
# Pages CI installs all workspaces because the root package.json
# defines them — no additional action needed as of 2025-06-01.
# If using pnpm, set install_command = "pnpm install --frozen-lockfile"
```

```toml
# pages.toml (alternative — separate build config file)
[build]
install_command = "pnpm install --frozen-lockfile"
build_command   = "pnpm --filter my-app build"
root_dir        = "/"
output_dir      = "apps/my-app/dist"
```

---

## Debugging Bundling Failures Locally

```bash
# Step 1: replicate the Pages CI build locally
npx wrangler pages dev ./dist \
  --compatibility-date=2024-09-23 \
  --compatibility-flag nodejs_compat

# Step 2: run a production-equivalent bundle check
npx wrangler pages deploy ./dist \
  --project-name my-app \
  --dry-run \
  --outdir /tmp/pages-bundle/

# Step 3: inspect the output bundle
ls -lh /tmp/pages-bundle/
cat /tmp/pages-bundle/_worker.js | head -50
```

---

## Anti-patterns

- **Importing `fs` or `path` without `nodejs_compat`** — always enable the flag when
  depending on any `node:*` module; do not expect browser polyfills to cover them.
- **Giant utility barrel files** — `import { helper } from "@acme/utils"` where
  `@acme/utils` re-exports 200 functions pulls in the entire package even if tree-shaking
  should remove them; export from focused sub-paths instead.
- **Using `require()` in Function code** — Pages Functions are ESM; use `import`.
- **Ignoring bundle size until deploy** — run esbuild `--analyze` in CI and fail the
  build if any Function exceeds 800 KB before compression.

## Gotchas

- The 1 MB limit is **per Function file** after compression, not the sum of all
  Functions. A route with many Functions can exceed 1 MB in aggregate without any
  single file tripping the limit.
- `wrangler pages dev` bundles on the fly and may tolerate some things the CI build
  does not (especially around module resolution order). Always run `wrangler pages
  deploy --dry-run` in CI to catch divergences.
- Pages Functions do not support Wrangler's `[build.upload.rules]` configuration;
  that is a Workers-only feature.
- Sourcemaps for Pages Functions are not automatically uploaded — set
  `upload_source_maps = true` in `wrangler.toml` (supported from Wrangler 3.x+).

## Verification

```bash
# Confirm bundle size is within limits
npx wrangler pages deploy dist --project-name my-app --dry-run --outdir /tmp/bundle
for f in /tmp/bundle/*.js; do
  size=$(gzip -c "$f" | wc -c)
  echo "$f: ${size} bytes compressed"
  [[ $size -gt 1048576 ]] && echo "WARNING: $f exceeds 1MB compressed"
done

# Confirm nodejs_compat resolves built-ins
curl -sf https://my-app.pages.dev/api/health | jq .
```

## Related

- `cloudflare-pages-functions-routing-rewrite-rules.md`
- `pages-functions-middleware-deploy-chain-validation.md`
- `workers-bundle-analysis-regression-ci.md`
- `workers-nodejs-compat-deploy-flags.md`
- `monorepo-deploy-pipeline-turborepo.md`

## Sources

- https://developers.cloudflare.com/pages/functions/
- https://developers.cloudflare.com/pages/functions/api-reference/
- https://developers.cloudflare.com/workers/runtime-apis/nodejs/
- https://developers.cloudflare.com/workers/wrangler/configuration/#bundling
- https://esbuild.github.io/api/#analyze
