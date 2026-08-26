# pnpm Overrides Peer Dependency Resolution Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Workers package in the example project monorepo pulls in two incompatible versions of a shared transitive dependency — for example, `hono@3` from one plugin and `hono@4` from another. `wrangler build` fails with duplicate-module errors or produces a bundle that silently uses the wrong version at runtime. The fix must not require forking the upstream packages; it must be repeatable across all developer machines and CI.

## Context

pnpm's `overrides` field in the root `package.json` forces every package in the workspace to resolve a dependency name to a single specified version, bypassing the normal semver negotiation. This is the equivalent of npm's `overrides` or Yarn's `resolutions`. In a monorepo where Workers packages must produce a single flat bundle with no duplicate runtime code, overrides are an essential tool for keeping bundle size and runtime behaviour predictable.

## Diagnosing the Problem

Use `pnpm why` to trace which packages pull in conflicting versions before writing any override.

```bash
# Find all resolved versions of a package across the workspace
pnpm why hono --recursive 2>&1 | grep -E "^(packages/|  hono)"

# Show the full dependency graph for one worker package
pnpm why hono --filter @example project/workers-api

# Check what's actually bundled after wrangler build
wrangler build --outdir dist 2>&1
ls -lh dist/*.js
# Then inspect for duplicates:
npx source-map-explorer dist/index.js --no-border-checks 2>/dev/null | head -40
```

A duplicate shows as two entries like `node_modules/hono/dist/...` and `node_modules/.pnpm/hono@3.x.x/...` in the bundle analysis.

## Writing pnpm Overrides

Add overrides to the **root** `package.json`. Scoped overrides let you target a specific parent package if a global pin would break other workspace packages.

```jsonc
// package.json (root)
{
  "name": "example project-monorepo",
  "private": true,
  "pnpm": {
    "overrides": {
      // Pin every consumer of hono to v4
      "hono": "^4.6.0",

      // Pin miniflare only for packages that use @cloudflare/workers-types
      "@cloudflare/workers-types>miniflare": "^3.20260601.0",

      // Force a security patch across all transitive consumers
      "undici": ">=6.21.0"
    },
    "peerDependencyRules": {
      // Suppress peer warnings for Vite's optional React peer dep
      "ignoreMissing": ["@vitejs/plugin-react"],
      // Treat hono@3 as compatible when a package declares hono@^3 || ^4
      "allowedVersions": {
        "hono": "4"
      }
    }
  }
}
```

After editing, reinstall to apply:

```bash
pnpm install
# Verify the resolution
pnpm why hono --recursive | grep "hono "
```

## Scoped Overrides for Selective Pinning

When a global override would break a package that legitimately needs the older version, use the `parent>child` syntax to scope it.

```jsonc
{
  "pnpm": {
    "overrides": {
      // Only override hono inside @example project/plugin-analytics, leave others alone
      "@example project/plugin-analytics>hono": "^4.6.0",

      // Override a deeply nested transitive dep under a specific top-level package
      "@example project/workers-api>some-lib>internal-pkg": "2.1.0"
    }
  }
}
```

Confirm the scoped override took effect:

```bash
pnpm why hono --filter @example project/plugin-analytics
# Should show only hono@4.x in the resolved graph
```

## Validating the Bundle in CI

Add a CI step that fails if duplicate modules appear in the Workers bundle. Use `wrangler build` and a simple duplicate check:

```bash
#!/usr/bin/env bash
# scripts/check-bundle-duplicates.sh
set -euo pipefail

WORKER=$1   # e.g. packages/workers-api
cd "$WORKER"

wrangler build --outdir /tmp/worker-dist 2>/dev/null

# Extract module paths from the bundle metadata
npx wrangler build --metafile=/tmp/meta.json --outdir /tmp/worker-dist 2>/dev/null || true

node - <<'EOF'
const meta = require('/tmp/meta.json');
const inputs = Object.keys(meta.inputs);
const pkgRe = /node_modules\/([^/]+\/[^/]+|[^@/][^/]*)\//;
const seen = new Map();
let fail = false;
for (const p of inputs) {
  const m = p.match(pkgRe);
  if (!m) continue;
  const pkg = m[1];
  if (seen.has(pkg) && seen.get(pkg) !== p) {
    console.error(`Duplicate: ${pkg}`);
    fail = true;
  }
  seen.set(pkg, p);
}
if (fail) process.exit(1);
EOF
```

```yaml
# .github/workflows/ci.yml
- name: Check Workers bundle for duplicates
  run: bash scripts/check-bundle-duplicates.sh packages/workers-api
```

## Anti-patterns

- Using `overrides` to pin to an older version to avoid fixing a real API break — the override masks the real problem and will cause confusing failures when the override is removed.
- Pinning to an exact version (`"hono": "4.6.0"`) instead of a caret range — patch security fixes in transitive deps get blocked.
- Applying a global override when only one package has the conflict — use the scoped `parent>child` form to avoid inadvertent breakage.
- Not running `pnpm install` after adding overrides in CI — the lockfile drift means the runner sees the old resolution.
- Silencing peer dependency warnings with `ignoreMissing` without investigating them — missing peers in Workers packages often cause silent runtime failures.

## Gotchas

- pnpm overrides affect the lockfile (`pnpm-lock.yaml`). Always commit the updated lockfile; a stale lockfile in CI will reinstall the old resolution.
- The `peerDependencyRules.allowedVersions` field suppresses warnings but does NOT change the resolved version — you still need an `overrides` entry to change the actual resolution.
- Cloudflare Workers bundles are ES modules with no `require()` — duplicate CJS modules that would fail in Node can pass bundling and only fail at runtime in the isolate.
- Some packages detect their own version at runtime and behave differently. A `hono@3` package overridden to `hono@4` binaries might still advertise version 3 in `package.json` if the package reads its own `version` field.
- `pnpm dedupe` (run after `pnpm install`) can automatically collapse compatible version ranges without overrides — try this first before writing a manual override.

## Verification

After applying overrides and reinstalling, run `pnpm ls hono --recursive --depth=3` and confirm only one version appears. Deploy to the Workers staging environment with `wrangler deploy --env staging` and run the integration test suite. Check the Cloudflare dashboard for CPU time anomalies that might indicate doubled initialization cost from a de-duplication that didn't fully take effect.

## Related

- pnpm-catalog-monorepo-dependency-alignment.md
- pnpm-workspace-protocol-version-resolution.md
- monorepo-pnpm-turborepo-2026.md
- git-submodule-vs-pnpm-workspace-workers-packages.md
- dependency-management-2026.md

## Sources

- https://pnpm.io/package_json#pnpmoverrides
- https://pnpm.io/package_json#pnpmpeerdependencyrules
- https://developers.cloudflare.com/workers/wrangler/bundling/
- https://pnpm.io/cli/dedupe
