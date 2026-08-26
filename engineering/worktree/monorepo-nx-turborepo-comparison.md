# Monorepo: Nx vs Turborepo Comparison

Date: 2026-08-17
Author: the platform team
Status: published

## Symptom

A growing pnpm workspace runs slow CI because every package
rebuilds on every PR, or the team cannot agree on whether to add
Nx or Turborepo on top of the existing workspace structure.

## Context

Both Nx and Turborepo are task orchestrators for monorepos: they
cache build outputs, parallelise tasks, and skip work when inputs
have not changed. Turborepo is a thin, file-hash-based runner; Nx
is a full platform with project graph inference, generators, and
a plugin ecosystem. Neither replaces the package manager (pnpm,
npm, yarn) — they sit on top of it.

## Caching Model

| Feature              | Nx                        | Turborepo               |
|----------------------|---------------------------|-------------------------|
| Local cache          | `~/.nx/cache`             | `node_modules/.cache/turbo` |
| Remote cache (free)  | Nx Cloud free tier        | Vercel Remote Cache     |
| Remote cache (self)  | Nx Cloud self-hosted / S3 | S3 community backends   |
| Cache key inputs     | file hashes + env vars    | file globs + env vars   |
| Distributed exec     | Nx Agents (paid)          | not built-in            |

```bash
# Turborepo remote cache (Vercel)
npx turbo login && npx turbo link

# Nx Cloud
npx nx connect
```

## Affected-Files Detection

Turborepo hashes `inputs` globs defined per task:

```jsonc
// turbo.json
{
  "tasks": {
    "build": {
      "inputs":  ["src/**", "package.json", "tsconfig*.json"],
      "outputs": ["dist/**"]
    }
  }
}
```

Nx builds a full project graph from `import` statements and
`project.json` declarations, then uses `nx affected`:

```bash
nx affected -t build --base=origin/main
nx affected -t test  --base=origin/main --parallel=4
```

Nx's graph is more accurate for cross-package TypeScript imports;
Turborepo's glob-based approach is simpler to reason about.

## Task Pipeline Definition

**Turborepo** (`turbo.json`):

```jsonc
{
  "tasks": {
    "build":     { "dependsOn": ["^build"],  "outputs": ["dist/**"] },
    "test":      { "dependsOn": ["build"],   "inputs": ["src/**", "test/**"] },
    "typecheck": { "dependsOn": ["^build"] },
    "deploy":    { "dependsOn": ["build", "test"], "cache": false }
  }
}
```

**Nx** (`nx.json` + `apps/web/project.json`):

```jsonc
// nx.json targetDefaults
{
  "build": { "dependsOn": ["^build"], "cache": true },
  "test":  { "cache": true, "inputs": ["default", "^default"] }
}
```

```jsonc
// apps/web/project.json
{
  "name": "web",
  "targets": {
    "build":  { "executor": "@nx/next:build" },
    "deploy": {
      "executor": "nx:run-commands",
      "options":  { "command": "wrangler pages deploy dist" },
      "dependsOn": ["build"]
    }
  }
}
```

## Plugin Ecosystem

| Area               | Nx                       | Turborepo        |
|--------------------|--------------------------|------------------|
| Next.js            | `@nx/next`               | none (use tasks) |
| Cloudflare Workers | community plugin         | none             |
| Storybook          | `@nx/storybook`          | none             |
| Generators         | built-in (`nx generate`) | none             |
| Migrations         | `nx migrate`             | none             |

Turborepo focuses on task running and delegates all scaffolding
to the package manager or external tools.

## When to Choose Each (Next.js + Workers Monorepo)

Choose **Turborepo** when:
- The team is small (1-5 engineers) and wants minimal config.
- Deployment targets are Vercel (free remote cache included).
- The monorepo has ≤ 10 packages.

Choose **Nx** when:
- The monorepo will grow to 10+ packages or apps.
- You want `nx affected` graph accuracy across TS path aliases.
- The team benefits from `nx generate` for new packages.
- Workers deploy steps need to participate in the dependency
  graph as Nx executors.
- Distributed CI (Nx Agents) is needed without custom matrix
  splitting logic.

## Anti-patterns

- Running both Nx and Turborepo in the same repo — they compete
  for cache and complicate debugging.
- Setting `cache: false` on `build` tasks "to be safe" — defeats
  the primary benefit of either tool.
- Defining `outputs` too broadly (e.g., `**`) — bloats the cache
  archive with node_modules or temp files.
- Skipping `dependsOn: ["^build"]` — tasks run out of order when
  a package imports a sibling that has not built yet.

## Gotchas

- `nx affected` uses `git diff` against the base branch; shallow
  clones (`fetch-depth: 1`) break it — use `fetch-depth: 0`.
- Turborepo's S3 remote cache is community-supported; the API
  may break across major Turbo versions.
- Nx Agents (distributed execution) require an Nx Cloud
  subscription at scale; the free tier has monthly limits.
- Turborepo does not auto-detect TypeScript project references;
  add them to `inputs` manually.

## Verification

```bash
# Turborepo — print task graph without running
pnpm turbo build --dry-run=json | jq '.tasks[].taskId'

# Nx — visualize project graph in browser
npx nx graph

# Confirm cache hit after second run
pnpm turbo build 2>&1 | grep "cache hit"
npx nx build web --verbose 2>&1 | grep "local cache"
```

## Related

- /documentation/categories/worktree/monorepo-pnpm-turborepo-2026.md
- /documentation/categories/worktree/monorepo-affected-builds-2026.md
- /documentation/categories/worktree/monorepo-ci-parallelization.md
- /documentation/categories/worktree/polyrepo-vs-monorepo-tradeoffs.md
- /documentation/categories/worktree/ci-cd-pipeline-2026.md

## Source URLs (verified 2026-08-17)

- https://turbo.build/repo/docs
- https://nx.dev/concepts/mental-model
- https://nx.dev/reference/nx-json
- https://turbo.build/repo/docs/reference/configuration
- https://nx.dev/nx-api/next
