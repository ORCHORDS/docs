# Turborepo Build Caching in a Workers Monorepo

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Workers monorepo has dozens of packages and every CI run rebuilds everything from scratch, making pipelines slow and expensive. You want Turborepo build caching — both local and remote via Cloudflare R2 — to skip unchanged packages automatically.

---

## Context

Turborepo's task pipeline understands inter-package dependencies and caches build outputs keyed by a hash of inputs (source files, env vars, lock file). When inputs haven't changed, Turbo replays cached outputs in milliseconds instead of re-running the build. For Workers monorepos the critical pipeline tasks are `build` (esbuild/tsc), `typecheck`, and `deploy` (wrangler). Remote caching extends this to CI by storing and retrieving cache artifacts from a remote store — Cloudflare R2 is a natural fit because it lives in the same ecosystem as Workers and has no egress fees. The `@turborepo/remote-cache` package provides an R2 adapter that plugs into Turbo's remote cache protocol.

---

## Section 1 — turbo.json Pipeline Configuration

```json
// turbo.json (repo root)
{
  "$schema": "https://turbo.build/schema.json",
  "remoteCache": {
    "enabled": true
  },
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "wrangler.toml", "tsconfig.json", "package.json"],
      "outputs": ["dist/**", ".wrangler/dist/**"]
    },
    "typecheck": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "tsconfig.json"],
      "outputs": []
    },
    "test": {
      "dependsOn": ["build"],
      "inputs": ["src/**", "test/**"],
      "outputs": ["coverage/**"]
    },
    "deploy": {
      "dependsOn": ["build", "typecheck", "test"],
      "inputs": ["dist/**", "wrangler.toml"],
      "outputs": [],
      "cache": false
    },
    "dev": {
      "cache": false,
      "persistent": true
    }
  }
}
```

```toml
# packages/api-gateway/wrangler.toml
name = "api-gateway"
main = "dist/index.js"
compatibility_date = "2025-01-01"

[build]
command = "npm run build"
cwd = "."
watch_dir = "src"

[[routes]]
pattern = "api.example.com/*"
zone_name = "example.com"
```

---

## Section 2 — Remote Cache with Cloudflare R2

Install the remote cache server and adapter:

```bash
# In the repo root
npm install --save-dev @turborepo/remote-cache
npm install --save-dev wrangler
```

Deploy the remote cache Worker to Cloudflare:

```typescript
// turbo-cache-worker/src/index.ts
import { createR2RemoteCache } from '@turborepo/remote-cache';

const handler = createR2RemoteCache({
  // The TURBO_TOKEN env var authorizes cache reads/writes
  tokenSecret: (env: Env) => env.TURBO_TOKEN,
  bucket: (env: Env) => env.TURBO_CACHE_BUCKET,
});

export default handler;

interface Env {
  TURBO_TOKEN: string;
  TURBO_CACHE_BUCKET: R2Bucket;
}
```

```toml
# turbo-cache-worker/wrangler.toml
name = "turbo-cache"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding = "TURBO_CACHE_BUCKET"
bucket_name = "turbo-build-cache"

[vars]
# TURBO_TOKEN is set as a secret: wrangler secret put TURBO_TOKEN
```

Configure Turbo to use the remote cache:

```bash
# .turbo/config.json (or set via env vars in CI)
# Create R2 bucket first
npx wrangler r2 bucket create turbo-build-cache

# Deploy the cache worker
cd turbo-cache-worker && npx wrangler deploy && cd ..

# Set the remote cache secret
npx wrangler secret put TURBO_TOKEN --name turbo-cache

# Export the same token for turbo CLI usage
export TURBO_TOKEN="your-secret-token"
export TURBO_API="https://turbo-cache.your-subdomain.workers.dev"
export TURBO_TEAM="orchords"
```

---

## Section 3 — CI Integration

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  build-and-test:
    runs-on: ubuntu-latest
    env:
      TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
      TURBO_API: ${{ secrets.TURBO_API }}
      TURBO_TEAM: orchords
      CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # Turbo needs full history for change detection

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Build all packages
        run: npx turbo build typecheck test --concurrency=4

      - name: Deploy changed Workers
        if: github.ref == 'refs/heads/main'
        run: |
          npx turbo deploy \
            --filter='...[origin/main]' \
            --concurrency=2
```

---

## Anti-patterns

- **Setting `cache: false` on `build`** — The build task is the most expensive; disabling its cache defeats the entire purpose. Only disable cache on `deploy` and `dev`.
- **Omitting `^build` in `dependsOn`** — Without `^build`, Turbo won't wait for upstream packages to build before building dependents. This causes stale import errors at runtime.
- **Committing `.turbo/` to git** — The `.turbo` directory contains local cache metadata and should be in `.gitignore`. Only the `turbo.json` config belongs in the repo.
- **Using the same `TURBO_TOKEN` across environments** — Use separate tokens for prod and CI. R2 bucket policies should restrict each token to the appropriate scope.
- **Forgetting `outputs` for build artifacts** — If `outputs` doesn't match the actual build output path, Turbo cannot restore the cache and will rebuild every time.

---

## Gotchas

- Turbo's remote cache protocol is content-addressed — changing `turbo.json` `inputs` patterns invalidates all existing cache entries for that task.
- `wrangler deploy` inside a Turbo pipeline requires `CLOUDFLARE_API_TOKEN` to be available as an env var in the pipeline execution context.
- `--filter='...[origin/main]'` uses git to detect changed packages; it requires `fetch-depth: 0` in the GitHub Actions checkout step.
- The R2 remote cache bucket will accumulate artifacts indefinitely — set an R2 lifecycle rule to expire objects older than 30 days to control storage costs.
- `persistent: true` on the `dev` task prevents Turbo from treating it as a build step; without it, `turbo dev` exits immediately after starting.

---

## Verification

```bash
# First run — cache MISS, full build
npx turbo build --summarize

# Second run — cache HIT, instant replay
npx turbo build --summarize
# Should show: "cache bypass" = 0, "cache hit" = N

# Check remote cache is being used
npx turbo build --verbosity=2 2>&1 | grep -i 'remote cache'

# List R2 cache objects
npx wrangler r2 object list turbo-build-cache --prefix turbo/
```

---

## Related

- `nx-workers-monorepo-affected-deploy.md`
- `git-worktree-parallel-feature-development.md`

---

## Sources

- Turborepo Remote Caching — https://turbo.build/repo/docs/core-concepts/remote-caching
- Cloudflare R2 Documentation — https://developers.cloudflare.com/r2
- Turborepo Task Pipeline Reference — https://turbo.build/repo/docs/reference/configuration
