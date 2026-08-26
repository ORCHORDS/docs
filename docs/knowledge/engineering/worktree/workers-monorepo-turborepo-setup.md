# Monorepo Setup with Turborepo for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have multiple Cloudflare Workers (API gateway, auth, payments, notifications) that share TypeScript types, utility libraries, and middleware. Deploying them independently causes drift — shared code gets copy-pasted, version mismatches appear between packages, and CI runs redundant builds. You need a monorepo that builds and deploys only what changed.

## Context

Turborepo is a high-performance build system for JavaScript/TypeScript monorepos. It understands task dependencies (e.g., `deploy` depends on `build`, `build` depends on `typecheck`), caches outputs locally and remotely, and can compute which packages were affected by a git change. Cloudflare Workers are deployed via `wrangler`, each requiring its own `wrangler.toml`. The challenge is wiring Turborepo's task pipeline to `wrangler deploy` per package while sharing code through npm workspaces.

## Solution

```
monorepo/
├── package.json                  # root workspace config
├── turbo.json                    # pipeline definition
├── packages/
│   ├── types/                    # @example-org/example-repo
│   │   ├── package.json
│   │   └── src/index.ts
│   ├── utils/                    # @example-org/example-repo
│   │   ├── package.json
│   │   └── src/index.ts
│   └── middleware/               # @example-org/example-repo
│       ├── package.json
│       └── src/index.ts
└── workers/
    ├── api-gateway/
    │   ├── package.json
    │   ├── wrangler.toml
    │   └── src/index.ts
    ├── auth/
    │   ├── package.json
    │   ├── wrangler.toml
    │   └── src/index.ts
    └── payments/
        ├── package.json
        ├── wrangler.toml
        └── src/index.ts
```

**Root `package.json`** — npm workspaces declaration:

```json
{
  "name": "orchords-monorepo",
  "private": true,
  "workspaces": [
    "packages/*",
    "workers/*"
  ],
  "scripts": {
    "build": "turbo run build",
    "typecheck": "turbo run typecheck",
    "lint": "turbo run lint",
    "deploy": "turbo run deploy",
    "deploy:affected": "turbo run deploy --filter=...[HEAD^1]"
  },
  "devDependencies": {
    "turbo": "^2.3.0",
    "typescript": "^5.5.0"
  }
}
```

**`turbo.json`** — task pipeline with caching:

```json
{
  "$schema": "https://turbo.build/schema.json",
  "remoteCache": {
    "enabled": true
  },
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "tsconfig.json", "package.json"],
      "outputs": ["dist/**"]
    },
    "typecheck": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "tsconfig.json"]
    },
    "lint": {
      "inputs": ["src/**", ".eslintrc*", "eslint.config.*"]
    },
    "test": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "test/**", "vitest.config.*"]
    },
    "deploy": {
      "dependsOn": ["build", "typecheck"],
      "inputs": ["src/**", "wrangler.toml", "dist/**"],
      "cache": false,
      "env": ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]
    }
  }
}
```

**`packages/types/package.json`** — shared types package:

```json
{
  "name": "@example-org/example-repo",
  "version": "1.0.0",
  "private": true,
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/index.js",
      "require": "./dist/index.cjs",
      "types": "./dist/index.d.ts"
    }
  },
  "scripts": {
    "build": "tsup src/index.ts --format esm,cjs --dts",
    "typecheck": "tsc --noEmit"
  },
  "devDependencies": {
    "tsup": "^8.0.0",
    "typescript": "^5.5.0"
  }
}
```

**`packages/types/src/index.ts`** — shared domain types:

```typescript
export interface User {
  id: string;
  email: string;
  role: 'admin' | 'member' | 'viewer';
  createdAt: string;
}

export interface ApiResponse<T> {
  data: T;
  meta: {
    requestId: string;
    timestamp: string;
  };
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export type WorkerEnv = {
  DB: D1Database;
  KV: KVNamespace;
  BUCKET: R2Bucket;
  ENVIRONMENT: 'development' | 'staging' | 'production';
  API_SECRET: string;
};
```

**`packages/middleware/src/index.ts`** — shared middleware:

```typescript
import type { WorkerEnv } from '@example-org/example-repo';

export type MiddlewareHandler<Env extends WorkerEnv = WorkerEnv> = (
  request: Request,
  env: Env,
  ctx: ExecutionContext
) => Promise<Response | null>;

export function withAuth<Env extends WorkerEnv>(
  handler: MiddlewareHandler<Env>
): MiddlewareHandler<Env> {
  return async (request, env, ctx) => {
    const authHeader = request.headers.get('Authorization');
    if (!authHeader?.startsWith('Bearer ')) {
      return new Response(JSON.stringify({ code: 'UNAUTHORIZED', message: 'Missing bearer token' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return handler(request, env, ctx);
  };
}

export function withCors(allowedOrigins: string[]): MiddlewareHandler {
  return async (request) => {
    const origin = request.headers.get('Origin') ?? '';
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': allowedOrigins.includes(origin) ? origin : '',
          'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type,Authorization',
          'Access-Control-Max-Age': '86400',
        },
      });
    }
    return null;
  };
}
```

**`workers/api-gateway/package.json`**:

```json
{
  "name": "@example-org/example-repo",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "build": "tsc --noEmit && wrangler deploy --dry-run --outdir dist",
    "typecheck": "tsc --noEmit",
    "deploy": "wrangler deploy",
    "dev": "wrangler dev"
  },
  "dependencies": {
    "@example-org/example-repo": "*",
    "@example-org/example-repo": "*",
    "@example-org/example-repo": "*"
  },
  "devDependencies": {
    "wrangler": "^3.80.0",
    "typescript": "^5.5.0"
  }
}
```

**`workers/api-gateway/wrangler.toml`**:

```toml
name = "orchords-api-gateway"
main = "src/index.ts"
compatibility_date = "2025-01-01"
compatibility_flags = ["nodejs_compat"]

[vars]
ENVIRONMENT = "production"

[[d1_databases]]
binding = "DB"
database_name = "orchords-prod"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "KV"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[env.staging]
name = "orchords-api-gateway-staging"
[env.staging.vars]
ENVIRONMENT = "staging"
```

**Affected-only deploy in CI (`deploy-affected.sh`)**:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Deploy only workers affected since the last successful deploy tag
LAST_TAG=$(git describe --tags --abbrev=0 --match="deploy/*" 2>/dev/null || echo "HEAD~1")
echo "Diffing against: $LAST_TAG"

# Turborepo computes the affected packages automatically
npx turbo run deploy --filter="...[${LAST_TAG}]" --log-order=stream

# Tag the successful deploy
git tag "deploy/$(date +%Y%m%dT%H%M%S)" HEAD
git push origin --tags
```

**Remote caching setup**:

```bash
# Authenticate with Turborepo Cloud (or self-hosted)
npx turbo login
npx turbo link

# In CI, set these environment variables:
# TURBO_TOKEN=<token from turbo.build dashboard>
# TURBO_TEAM=<team slug>
```

## Implementation Details

- `"dependsOn": ["^build"]` means "run build in all dependencies before running build in this package". The `^` prefix indicates upstream workspace dependencies, ensuring `@example-org/example-repo` builds before `@example-org/example-repo` which depends on it.
- Turborepo hashes all `inputs` to determine cache hits. The `deploy` task sets `cache: false` because deploying to Cloudflare is a side-effectful operation — the Worker is live after it runs — so Turborepo should never skip it based on a cache hit.
- The `--filter=...[HEAD^1]` glob means "this package and all packages that transitively depend on anything changed between HEAD and HEAD^1". In CI, replace `HEAD^1` with the merge base: `$(git merge-base origin/main HEAD)`.
- Each Worker's `wrangler.toml` is self-contained. There is no root `wrangler.toml`. This ensures `wrangler dev` works correctly inside each worker directory without global configuration leaking.
- The `outputs: ["dist/**"]` declaration allows Turborepo to restore cached build artifacts to other machines, so CI agents that did not run the build can still deploy.

## Anti-patterns

- **Shared `wrangler.toml` at root**: Wrangler does not support inheritance; a root config creates confusion and is not applied per-worker.
- **`cache: true` on deploy**: Marking deploy as cacheable causes Turborepo to skip the actual `wrangler deploy` call if inputs have not changed. Deployments must always run.
- **`"*"` version for workspace packages in production packages**: Using `"*"` is correct only for `private: true` packages. Public packages published to npm must pin exact workspace versions.
- **Running `turbo run build && turbo run deploy` sequentially in separate commands**: This loses Turborepo's task graph awareness. Use `deploy` with `dependsOn: ["build"]` so Turborepo handles ordering and parallelism.

## Gotchas

- Wrangler does not read `NODE_PATH` or npm workspace symlinks at bundle time — it uses its own bundler (esbuild). Shared packages must be installed as proper workspace dependencies (listed in `package.json`), not merely symlinked manually.
- `turbo run deploy --filter=...` is computed at the time of the command. If you push a tag after a failed deploy, the next run may include more packages than expected. Verify the filter output with `--dry-run` before a production deploy.
- Turborepo remote cache does not cache `cache: false` tasks by definition. Do not set `cache: false` on `build` — only on `deploy`.
- The `env` array in `turbo.json` tasks causes those environment variables to be included in the hash. If `CLOUDFLARE_API_TOKEN` is rotated, all deploy tasks that reference it will get a cache miss — which is the correct behaviour.

## Verification

```bash
# Confirm workspace packages are linked correctly
npm ls --workspaces --depth 1

# Dry-run the full pipeline — shows what would run
npx turbo run deploy --dry-run=json | jq '.tasks[] | {package: .taskId, cache: .cache.status}'

# Confirm only affected workers are targeted
npx turbo run deploy --filter='...[HEAD^1]' --dry-run=json | jq '[.tasks[].taskId]'

# Check remote cache hit rate after first CI run
npx turbo run build --summarize
# Outputs: .turbo/runs/<id>.json with cache hit/miss per task
```

## Related

- `workers-git-hooks-husky-setup.md` — pre-push hook that runs `wrangler deploy --dry-run`
- `workers-semantic-versioning-automation.md` — tagging and releasing shared packages
- `workers-dependency-update-workflow.md` — Renovate grouping for Turborepo and wrangler updates
- `release-branch-strategy.md` — how release branches interact with monorepo deploys

## Sources

- https://turbo.build/repo/docs/crafting-your-repository/creating-an-internal-package
- https://turbo.build/repo/docs/reference/configuration#dependson
- https://developers.cloudflare.com/workers/wrangler/configuration/
- https://turbo.build/repo/docs/core-concepts/remote-caching
