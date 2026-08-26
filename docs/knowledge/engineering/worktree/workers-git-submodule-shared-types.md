# Shared TypeScript Types Across Workers Repos via Git Submodules

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Multiple Cloudflare Workers in separate repositories need to share TypeScript type definitions — request/response schemas, Durable Object state shapes, KV value types, or RPC interface contracts. Copying types by hand diverges quickly. Publishing an npm package for types-only requires a full publish pipeline for every change. Git submodules offer a middle path: a single source of truth versioned with git, consumed without an npm registry.

## Context

Git submodules embed one repository as a subdirectory of another, pinned to a specific commit. The parent repository tracks the submodule at a SHA, not a branch, so updates are explicit and auditable. For a types-only package this means:

- Zero runtime dependencies shipped to the Worker
- TypeScript sees the types directly via `paths` or `references`
- Updating shared types is a deliberate PR action (`git submodule update --remote`)
- CI must initialize submodules on checkout (`git submodule update --init --recursive`)

## Solution

### 1. Create the shared types repository

```bash
# In a new repo: github.com/example-org/example-repo
mkdir workers-shared-types && cd workers-shared-types
git init
```

Repository structure:

```
workers-shared-types/
  src/
    kv.ts          # KV value shapes
    do.ts          # Durable Object state interfaces
    api.ts         # Request/response schemas
    env.ts         # Shared Env interface fragments
    index.ts       # Re-export barrel
  tsconfig.json
  package.json
```

```typescript
// src/api.ts
export interface RateLimitRequest {
  clientId: string;
  endpoint: string;
  windowMs: number;
}

export interface RateLimitResponse {
  allowed: boolean;
  remaining: number;
  resetAt: number; // Unix ms
}

export interface ErrorResponse {
  error: string;
  code: string;
  requestId: string;
}
```

```typescript
// src/kv.ts
export interface SessionValue {
  userId: string;
  expiresAt: number;
  scopes: string[];
}

export interface ConfigValue {
  version: number;
  updatedAt: string;
  data: Record<string, unknown>;
}
```

```typescript
// src/do.ts
export interface CounterState {
  count: number;
  lastUpdated: string;
  ownerId: string;
}

export interface RateLimiterState {
  requests: number[];
  windowStart: number;
}
```

```typescript
// src/index.ts
export * from './api';
export * from './kv';
export * from './do';
export * from './env';
```

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "declaration": true,
    "declarationMap": true,
    "noEmit": true
  },
  "include": ["src"]
}
```

### 2. Add the submodule to a consumer Worker repo

```bash
# Inside the consumer Worker repository
git submodule add \
  https://github.com/example-org/example-repo \
  shared/types

# Commit the .gitmodules file and the submodule pointer
git add .gitmodules shared/types
git commit -m "chore(shared-types): add workers-shared-types submodule"
```

This creates `.gitmodules`:

```ini
[submodule "shared/types"]
  path = shared/types
  url = https://github.com/example-org/example-repo
  branch = main
```

### 3. Configure TypeScript to resolve the submodule

```json
// tsconfig.json (consumer Worker)
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "paths": {
      "@shared/types": ["./shared/types/src/index.ts"],
      "@shared/types/*": ["./shared/types/src/*"]
    }
  },
  "include": ["src", "shared/types/src"]
}
```

Usage in the Worker:

```typescript
// src/handler.ts
import type { RateLimitRequest, RateLimitResponse } from '@shared/types';

export function buildRateLimitResponse(
  req: RateLimitRequest,
  remaining: number
): RateLimitResponse {
  return {
    allowed: remaining > 0,
    remaining,
    resetAt: Date.now() + req.windowMs,
  };
}
```

Wrangler does not bundle `@shared/types` at runtime — it resolves only during `tsc` type-checking. The compiled output contains no import from the submodule, confirming zero runtime overhead.

### 4. Submodule update workflow

When shared types change, consumer repos must explicitly update their pinned SHA:

```bash
# Update the submodule to the latest commit on its tracked branch
git submodule update --remote --merge shared/types

# Review what changed
git diff shared/types

# Run typechecking to catch any breaking type changes
npx tsc --noEmit

# Commit the updated submodule pointer
git add shared/types
git commit -m "chore(shared-types): update to latest shared types"
```

For bulk updates across many consumer repos, use a script:

```bash
#!/bin/bash
# scripts/update-shared-types.sh
# Run from each consumer repo root

set -euo pipefail

SUBMODULE_PATH="shared/types"

echo "Updating $SUBMODULE_PATH..."
git submodule update --remote --merge "$SUBMODULE_PATH"

echo "Type-checking..."
npx tsc --noEmit

NEW_SHA=$(git -C "$SUBMODULE_PATH" rev-parse --short HEAD)
echo "Updated to $NEW_SHA"

git add "$SUBMODULE_PATH"
git commit -m "chore(shared-types): update to $NEW_SHA"

echo "Done. Open a PR to merge this update."
```

### 5. CI submodule initialization

```yaml
# .github/workflows/ci.yml (relevant excerpt)
jobs:
  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: 'recursive'   # initialize + update all submodules
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }

      - run: npm ci
      - run: npx tsc --noEmit
```

For private submodule repos, use a deploy key or a GitHub App token:

```yaml
      - uses: actions/checkout@v4
        with:
          submodules: 'recursive'
          token: ${{ secrets.SUBMODULE_PAT }}   # PAT with repo read scope
```

## Implementation Details

- The submodule pointer in the parent repo is a plain git object (a "gitlink") containing the SHA of the submodule commit. Running `git log shared/types` in the parent shows the history of pointer updates, not the submodule's own history.
- `"branch": "main"` in `.gitmodules` tells `git submodule update --remote` which branch to track, but the parent still pins to a SHA. Pinning is intentional — it prevents silent breakage from upstream changes.
- `noEmit: true` in the submodule's `tsconfig.json` is critical: you do not want `tsc` inside the submodule to emit JS into the Worker's output.
- Wrangler's bundler (esbuild) follows TypeScript `paths` during bundling. Verify the path aliases are also present in any `esbuild` config if you have a custom build step.

## npm workspace vs submodule tradeoffs

| | Git Submodule | npm Workspace |
|---|---|---|
| Registry required | No | No (workspace protocol) |
| Versioning | Pinned SHA (explicit) | Workspace symlink (implicit latest) |
| Breaking change isolation | Strong (must explicitly update) | Weak (workspace always latest) |
| CI complexity | Medium (submodule init step) | Low |
| Works across org repos | Yes | No (monorepo only) |
| Runtime bundle | Zero (type-only) | Depends on package contents |
| Developer friction | Medium (update workflow) | Low |

Use a submodule when types are shared across separate repositories. Use an npm workspace when everything lives in a monorepo.

## Anti-patterns

- **Importing runtime code from the submodule**: if the submodule grows beyond types (adds utility functions), the `noEmit` guard breaks and you start bundling shared code into Workers — use an npm package instead.
- **Not pinning the submodule to a SHA**: `git submodule update --remote` without committing the result leaves the submodule detached and other developers see a dirty state.
- **Using HTTPS URLs for private submodules in CI without token configuration**: the checkout will silently fail or produce an empty directory.
- **Deeply nested submodules**: submodule-of-submodule hierarchies are hard to reason about; keep it to one level.

## Gotchas

- Fresh clones of the parent repo do NOT automatically initialize submodules. Developers must run `git clone --recurse-submodules <url>` or `git submodule update --init --recursive` after a plain clone.
- Renaming or moving a submodule directory requires editing `.gitmodules` manually AND running `git submodule sync` before the next update.
- If the shared types repo is renamed or transferred in GitHub, all consumer `.gitmodules` files need updating.
- `actions/checkout@v4` with `submodules: true` only initializes one level deep; use `submodules: 'recursive'` for nested cases.

## Verification

```bash
# Confirm submodule is initialized
git submodule status
# Output: <sha> shared/types (heads/main)

# Verify TypeScript resolves the path alias
npx tsc --noEmit --traceResolution 2>&1 | grep 'shared/types'

# Check no runtime imports leak into bundle
npx wrangler deploy --dry-run --outdir dist/
grep -r 'shared/types' dist/ || echo 'Clean — no submodule code in bundle'

# Confirm CI checkout includes submodule content
ls shared/types/src/
```

## Related

- `documentation/docs/policies/worktree/workers-release-branch-strategy.md`
- `documentation/docs/policies/worktree/workers-conventional-commits-enforcement.md`
- `documentation/docs/policies/worktree/sparse-checkout-large-monorepo.md`

## Sources

- https://git-scm.com/book/en/v2/Git-Tools-Submodules
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/accessing-contextual-information-about-workflow-runs
- https://developers.cloudflare.com/workers/wrangler/bundling/
