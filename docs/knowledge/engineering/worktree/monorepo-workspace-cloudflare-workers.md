# pnpm Workspace Monorepo for Cloudflare Workers + Next.js Pages

Date:   2026-08-22
Author: example.com
Status: stable

## Symptom

Types are duplicated between the Workers backend and the Next.js frontend,
`pnpm install` in one package doesn't reflect changes in a sibling package,
Turborepo runs every task on every PR even when only one package changed,
and Wrangler deploys pick up transitive dependencies that were never
intended for the Workers runtime.

## Context

A pnpm workspace monorepo centralises dependency management and enables
local cross-package imports via the `workspace:` protocol. Turborepo
provides a task graph with caching. The key structural challenge for a
Workers + Pages monorepo is that the Worker is a V8-isolate bundle (no
Node.js built-ins, 1 MB limit) while the Next.js frontend is a Node.js
process deployed to Cloudflare Pages via `@cloudflare/next-on-pages`.
Shared types and utilities must be careful not to pull in Node.js-specific
code into the Worker bundle.

---

## 1. Repository Layout

```
repo-root/
├── pnpm-workspace.yaml
├── turbo.json
├── package.json               (root devDeps: turbo, typescript, eslint)
│
├── worker/                    Cloudflare Worker (Hono or plain fetch)
│   ├── package.json
│   ├── wrangler.toml
│   ├── src/
│   └── tsconfig.json
│
├── frontend/                  Next.js App Router → Pages
│   ├── package.json
│   ├── next.config.ts
│   ├── src/
│   └── tsconfig.json
│
└── packages/
    ├── types/                 Shared TypeScript interfaces + Zod schemas
    │   ├── package.json
    │   └── src/index.ts
    │
    └── utils/                 Pure-JS utilities (no Node built-ins)
        ├── package.json
        └── src/index.ts
```

---

## 2. pnpm-workspace.yaml

```yaml
packages:
  - 'worker'
  - 'frontend'
  - 'packages/*'
```

Root `package.json`:

```json
{
  "name": "my-project",
  "private": true,
  "scripts": {
    "build":     "turbo run build",
    "dev":       "turbo run dev --parallel",
    "lint":      "turbo run lint",
    "typecheck": "turbo run typecheck",
    "test":      "turbo run test"
  },
  "devDependencies": {
    "turbo":      "^2.0.0",
    "typescript": "^5.5.0",
    "eslint":     "^9.0.0"
  }
}
```

---

## 3. Shared Packages with workspace: Protocol

`packages/types/package.json`:

```json
{
  "name": "@my-project/types",
  "version": "0.0.0",
  "private": true,
  "main":    "./src/index.ts",
  "types":   "./src/index.ts",
  "exports": {
    ".": "./src/index.ts"
  }
}
```

No build step is needed for a types-only package if consumers all use
`tsx` / `ts-node` or Vite's TypeScript resolution. For a published
package or when Wrangler needs `.js` output, add a `tsup` build step.

Consuming from the Worker:

```json
// worker/package.json
{
  "dependencies": {
    "@my-project/types": "workspace:*",
    "@my-project/utils": "workspace:*"
  }
}
```

`workspace:*` resolves to the local package at any version; `workspace:^`
enforces semver range. Use `workspace:*` for private monorepo packages.

Import in Worker code:

```ts
// worker/src/routes/users.ts
import type { User } from '@my-project/types';
import { slugify }   from '@my-project/utils';
```

---

## 4. Turborepo Task Graph

`turbo.json`:

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".next/**", "!.next/cache/**"]
    },
    "typecheck": {
      "dependsOn": ["^build"]
    },
    "lint": {
      "outputs": []
    },
    "test": {
      "dependsOn": ["^build"],
      "outputs": ["coverage/**"]
    },
    "test:integration": {
      "dependsOn": ["build"],
      "outputs": []
    },
    "dev": {
      "cache":     false,
      "persistent": true
    }
  }
}
```

`^build` means "build all packages this package depends on first". This
ensures `packages/types` is built before `worker` and `frontend` are
type-checked or tested.

---

## 5. Filtering Deploys by Changed Packages

Only redeploy packages that actually changed. Turborepo's `--filter` flag
integrates with Git to compute the affected set:

```bash
# Deploy only packages changed since the last release tag:
pnpm exec turbo run deploy \
  --filter='...[$(git describe --tags --abbrev=0)]'

# In CI: changed since the base branch of the PR:
pnpm exec turbo run deploy \
  --filter="...[origin/main]"
```

`...` (three dots) means "this package and all packages that depend on
it". If `packages/types` changes, both `worker` and `frontend` are in the
affected set because they depend on it.

Add a `deploy` script to each deployable package:

```json
// worker/package.json
{
  "scripts": {
    "deploy": "wrangler deploy --config wrangler.toml --env production"
  }
}
```

```json
// frontend/package.json
{
  "scripts": {
    "deploy": "wrangler pages deploy .next/standalone --project-name=my-project"
  }
}
```

---

## 6. Type Sharing Between Worker and Frontend

The key rule: `packages/types` must contain **only** types and Zod schemas
with zero runtime imports that touch Node.js built-ins.

```ts
// packages/types/src/index.ts
import { z } from 'zod';   // OK: zod works in Workers runtime

export const UserSchema = z.object({
  id:    z.string().uuid(),
  email: z.string().email(),
  name:  z.string().min(1),
});

export type User = z.infer<typeof UserSchema>;

// Route type: Worker handler signature shared with frontend's API client.
export type ApiRoutes = {
  '/users/:id': {
    GET: { response: User };
  };
};
```

Frontend can generate a type-safe fetch client from `ApiRoutes` using
`hono/client` or a custom typed fetch wrapper without any runtime cost.

Boundary: never import `packages/utils` code that uses `crypto`,
`fs`, `path`, or `process` into the Worker unless the Worker's
`wrangler.toml` has `compatibility_flags = ["nodejs_compat"]` set
and those modules are genuinely supported in the Workers runtime.

---

## 7. wrangler.toml for Workspace Monorepo

```toml
# worker/wrangler.toml
name            = "my-project-api"
main            = "src/index.ts"
compatibility_date = "2024-09-23"

# Wrangler resolves workspace packages from the lockfile.
# No extra configuration needed; pnpm hoists correctly.

[[d1_databases]]
binding    = "DB"
database_name = "my-project-prod"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[env.production]
vars = { RELEASE_VERSION = "0.0.0" }

[env.preview]
vars = { RELEASE_VERSION = "preview" }
```

Wrangler's bundler (esbuild) follows `node_modules` symlinks created by
pnpm's hoisting. Ensure `.npmrc` in the root does NOT set
`shamefully-hoist=false` unless you also configure Wrangler's `node_modules`
resolution path explicitly.

---

## Anti-patterns

- Putting `packages/utils` code that imports `path` or `fs` into the
  Worker bundle. Even with `nodejs_compat`, many Node.js APIs are stubs
  that throw at runtime.
- Using `"main": "./dist/index.js"` in a shared package but forgetting to
  rebuild it after changes during local dev. Use `"main": "./src/index.ts"`
  and let each consumer's bundler handle transpilation.
- Setting `workspace:^version` for shared packages. In a private monorepo
  this creates unnecessary version constraint friction; `workspace:*` is
  almost always correct.
- Running `pnpm install` inside a subdirectory. Always install from the
  repo root so the single lockfile is updated consistently.
- Adding `turbo` as a local dependency per-package instead of at the root.

---

## Gotchas

- pnpm creates symlinks in `node_modules/.pnpm/` using a content-addressable
  store. Wrangler's bundler follows these symlinks correctly, but some tools
  (jest, older esbuild versions) need `symlinks: true` in their config.
- Turborepo's remote cache uses a content hash of inputs. Changing a file
  that is in `turbo.json`'s `globalDependencies` list invalidates ALL tasks.
  Keep that list tight: only `turbo.json`, root `tsconfig.json`, and
  `.npmrc`.
- `workspace:*` in `package.json` is a pnpm-specific protocol. If a
  `package.json` is ever published to npm, pnpm rewrites `workspace:*`
  to the resolved version automatically. Private packages never need this,
  but it explains why the protocol is safe to use everywhere.
- Cloudflare Pages does not read `pnpm-workspace.yaml` natively. You must
  set the build command to `cd ../.. && pnpm install && pnpm --filter
  frontend run build` from the Pages project settings or via a custom build.

---

## Verification

```bash
# Confirm workspace links are resolved correctly:
pnpm list --filter worker --depth 2

# Confirm Turborepo sees the right task graph:
pnpm exec turbo run build --dry-run=json | jq '.tasks[].taskId'

# Check that no Node.js built-ins leaked into the Worker bundle:
pnpm exec wrangler deploy --dry-run --outdir dist/
grep -r "require('path')\|require('fs')" dist/ && echo "LEAK DETECTED"
```

---

## Related

- documentation/docs/policies/worktree/github-actions-wrangler-deploy-pipeline.md
- documentation/docs/policies/worktree/pr-readiness-checklist-workers-projects.md
- documentation/docs/policies/worktree/conventional-commits-automated-changelog.md
- documentation/docs/policies/worktree/git-branching-cloudflare-preview-environments.md

---

## Source URLs

- https://pnpm.io/workspaces
- https://turbo.build/repo/docs/crafting-your-repository/structuring-a-repository
- https://developers.cloudflare.com/workers/wrangler/bundling/
- https://developers.cloudflare.com/pages/configuration/build-configuration/
- https://github.com/nicolo-ribaudo/tc39-proposal-temporal
