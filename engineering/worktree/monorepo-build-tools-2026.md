# monorepo-build-tools-2026

**Issue:** A team has 30 packages in one repo. The team reads about Lerna, Nx, Turborepo, Rush, pnpm workspaces. The team needs the 2026 decision framework.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 build tools compared

| Tool | Cache | Plugins | Language | Best for |
|---|---|---|---|---|
| pnpm workspaces | Content-addressable store | Via pnpm | JS/TS | JS/TS, fast, simple |
| Turborepo | Local + remote | Pipeline files (`turbo.json`) | JS/TS | JS/TS monorepos |
| Nx | Local + remote | Rich plugin ecosystem | JS/TS, Java, Go | Multi-language, large scale |
| Lerna | None (relies on Nx) | Limited | JS/TS | Niche (mostly superseded by Nx) |
| Rush | Heft-based, phased | Strict policies | JS/TS | Enterprise, large monorepos |

## The 5-step decision rule

1. **Pure JS/TS, <10 packages, want simplicity** → pnpm workspaces alone.
2. **JS/TS, want pipeline + remote cache** → Turborepo + pnpm.
3. **Multi-language (Java + JS + Go), 50+ packages** → Nx.
4. **Enterprise, 100+ packages, strict policies** → Rush.
5. **Lerna alone** is mostly superseded; use Lerna + Nx or migrate to Nx.

## The 5 best practices

1. **Content-addressable storage** (pnpm CAS, Turborepo cache) for fast repeated builds.
2. **Remote cache** (Vercel, Nx Cloud) for CI deduplication.
3. **Affected-only testing** (`nx affected`, `turbo run --filter=...[origin/main]`).
4. **Pipeline files** declare dependencies; build tools compute topological order.
5. **Versioning** via Changesets (independent per-package) or fixed (single version).

## Gotchas

- pnpm's strict node_modules layout breaks some tools that walk up `node_modules`.
- Turborepo's `turbo.json` doesn't natively support graph-aware task DAGs; use Nx for richer task graphs.
- Nx's plugin model is its strength but also its lock-in.
- Lerna 8+ defaults to Nx as the task runner.

## Source URLs (verified 2026-08-10)

- https://pnpm.io/workspaces
- https://turbo.build/repo/docs
- https://nx.dev/getting-started/intro
- https://rushjs.io/
- https://lerna.js.org/
