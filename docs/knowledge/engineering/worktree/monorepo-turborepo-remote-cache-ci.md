# Monorepo Turborepo Remote Cache in GitHub Actions CI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A pnpm + Turborepo monorepo takes 12+ minutes to build and test in CI on every push because task outputs are not cached between runs, even when no relevant source files have changed.

## Context
Turborepo's remote cache stores task output artifacts (build artefacts, test results, type-check outputs) on a remote backend keyed by a hash of all inputs: source files, environment variables, and dependent task hashes. When a CI run finds a cache hit, it replays the cached output in milliseconds rather than re-executing. Vercel hosts a free remote cache accessible via `TURBO_TOKEN` and `TURBO_TEAM`, but self-hosted alternatives exist using Turborepo's open remote cache protocol over any S3-compatible store. This article covers both the Vercel-hosted path and a self-hosted Cloudflare R2 path.

## turbo.json Pipeline Configuration
```json
{
  "$schema": "https://turbo.build/schema.json",
  "ui": "tui",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "package.json", "tsconfig.json", "wrangler.toml"],
      "outputs": ["dist/**", ".wrangler/tmp/**"]
    },
    "test": {
      "dependsOn": ["build"],
      "inputs": ["src/**", "test/**", "vitest.config.ts"],
      "outputs": ["coverage/**"],
      "cache": true
    },
    "typecheck": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "tsconfig.json"],
      "outputs": [],
      "cache": true
    },
    "lint": {
      "inputs": ["src/**", "*.config.*", ".eslintrc*"],
      "outputs": [],
      "cache": true
    },
    "deploy": {
      "dependsOn": ["build", "test", "typecheck"],
      "cache": false
    }
  }
}
```

## Vercel Remote Cache: GitHub Actions Setup
```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

env:
  TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
  TURBO_TEAM: ${{ vars.TURBO_TEAM }}
  TURBO_REMOTE_ONLY: false   # fall back to local cache on miss

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 10

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Build, test, typecheck (with remote cache)
        run: pnpm turbo build test typecheck lint --summarize

      - name: Upload turbo summary
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: turbo-summary
          path: .turbo/runs/*.json
```

## Self-hosted Cache with Cloudflare R2
```typescript
// turbo-cache-server/src/index.ts
// A minimal Cloudflare Worker implementing the Turborepo remote cache protocol

export interface Env {
  TURBO_CACHE: R2Bucket;
  TURBO_TOKEN: string;
}

function authorize(request: Request, env: Env): boolean {
  const auth = request.headers.get("Authorization");
  return auth === `Bearer ${env.TURBO_TOKEN}`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (!authorize(request, env)) {
      return new Response("Unauthorized", { status: 401 });
    }

    const url = new URL(request.url);
    // Path: /v8/artifacts/<hash>
    const match = url.pathname.match(/^\/v8\/artifacts\/([a-f0-9]+)$/);
    if (!match) return new Response("Not Found", { status: 404 });

    const key = `artifacts/${match[1]}`;

    if (request.method === "HEAD") {
      const obj = await env.TURBO_CACHE.head(key);
      return obj
        ? new Response(null, { status: 200 })
        : new Response(null, { status: 404 });
    }

    if (request.method === "GET") {
      const obj = await env.TURBO_CACHE.get(key);
      if (!obj) return new Response("Not Found", { status: 404 });
      return new Response(obj.body, {
        headers: { "Content-Type": "application/octet-stream" },
      });
    }

    if (request.method === "PUT") {
      await env.TURBO_CACHE.put(key, request.body!);
      return new Response(null, { status: 200 });
    }

    return new Response("Method Not Allowed", { status: 405 });
  },
} satisfies ExportedHandler<Env>;
```

## Connecting Turbo to the Self-hosted Cache
```yaml
# .github/workflows/ci-r2-cache.yml
name: CI (R2 cache)

on:
  push:
    branches: [main]
  pull_request:

env:
  TURBO_API: https://turbo-cache.orchords.workers.dev
  TURBO_TOKEN: ${{ secrets.TURBO_CACHE_TOKEN }}
  TURBO_TEAM: orchords

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 10

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Run CI pipeline
        run: pnpm turbo build test typecheck lint

      - name: Show cache hit rate
        if: always()
        run: |
          pnpm turbo build test typecheck lint --dry=json \
            | jq '.tasks[] | {task: .taskId, cache: .cache.status}'
```

## Cache Pruning for Monorepo Deployments
```bash
# Only build and deploy packages affected by changes in this PR
# turbo prune creates a minimal sub-repo with only the affected package graph

pnpm turbo prune --scope=@example-org/example-repo --docker

# The pruned output lives in ./out/
# out/json/  — package.json files only (for installing deps)
# out/full/  — full source for building

# Use in a Docker-based deploy:
# Stage 1: install from out/json
# Stage 2: copy out/full, run turbo build --filter=@example-org/example-repo
```

## Anti-patterns
- Setting `TURBO_REMOTE_ONLY=true` without a guaranteed cache server — this disables local cache fallback, causing total cache misses when the remote is unavailable
- Including `node_modules` in `outputs` — this bloats cached artifacts and causes cache invalidation on any transitive dep change
- Omitting `wrangler.toml` from the `inputs` of the `build` task in a Workers project — compatibility date changes will not invalidate the cache
- Sharing a single `TURBO_TOKEN` across multiple repositories — invalidate the token if a repository is archived or becomes public

## Gotchas
- Turborepo hashes environment variables listed in `globalEnv` or per-task `env`; any variable not explicitly listed is excluded from the hash, risking stale cache hits
- The Vercel remote cache is free up to 10 GB of storage but evicts items after 30 days of inactivity — cold starts after a holiday period are expected
- `pnpm turbo --filter=...[origin/main]` selects packages changed relative to `origin/main`; ensure the action fetches enough git depth for the comparison (`fetch-depth: 0`)
- R2 does not support bucket-level TTL policies natively; implement artifact expiry with a scheduled Worker that lists and deletes objects older than N days

## Verification
```bash
# First run: all cache misses, full build
pnpm turbo build test typecheck --force

# Second run: all tasks should be FULL TURBO (100% cache hits)
pnpm turbo build test typecheck

# Inspect what was cached
ls -lh .turbo/cache/

# Dry-run to see what would execute
pnpm turbo build test --dry=json | jq '.tasks[].cache'
```

## Related
- `/documentation/docs/policies/worktree/monorepo-pnpm-turborepo-2026.md`
- `/documentation/docs/policies/worktree/monorepo-affected-builds-2026.md`
- `/documentation/docs/policies/worktree/ci-cache-optimization-github-actions.md`
- `/documentation/docs/policies/worktree/monorepo-ci-parallelization.md`
- `/documentation/docs/policies/worktree/monorepo-workspace-cloudflare-workers.md`

## Sources
- https://turbo.build/repo/docs/core-concepts/remote-caching
- https://turbo.build/repo/docs/reference/configuration
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
- https://github.com/ducktors/turborepo-remote-cache
