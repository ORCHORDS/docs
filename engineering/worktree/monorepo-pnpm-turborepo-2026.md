# monorepo-pnpm-turborepo-2026

**Issue:** A team has 8 apps and 12 shared packages across 3 git repos. A change to the types package requires PRs in 4 repos, coordinated releases, and version-bump coordination. Six weeks later, version 2.0 of types breaks 3 apps in production.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Polyrepo (one repo per app or package) creates coordination overhead for any cross-cutting change. Version drift, refactor friction, and "which version of types is the API actually using" are routine problems. The team wants shared code, atomic refactors, and one tooling baseline.

## Root cause

A monorepo is one version-controlled repository holding multiple projects, libraries, and services that may be deployed independently. The monorepo tooling has matured: pnpm workspaces, Turborepo, and Nx are the 2026 defaults. Bazel is the polyglot enterprise pick.

## The three-layer stack

A JavaScript/TypeScript monorepo is three layers:

1. **Workspace manager** — resolves dependencies, links local packages. pnpm is the 2026 default: content-addressable store, strict isolation, `workspace:*` protocol.
2. **Task runner** — decides what to build, in what order, what to cache. Turborepo (simplicity) or Nx (power).
3. **Shared tooling** — lint, format, type-check, hooks. Biome or ESLint+Prettier, tsconfig.base.json, husky or lefthook, changesets for versioning.

The three layers are largely orthogonal. Mix and match.

## The 2026 decision matrix

| Tool | Best for | Languages | Caching | Code gen | Cost |
|---|---|---|---|---|---|
| pnpm workspaces | Any size (lightweight) | Any | None (separate) | No | Free |
| Turborepo 2.x | 2-20 packages, small-mid teams | JS/TS only | Yes (Vercel free / self-host) | No | Free |
| Nx 22 | 20+ packages, 10-500+ engineers | JS/TS + plugins | Yes (Nx Cloud paid / self-host) | Yes | $19/contributor/mo |
| Bazel | 1,000+ engineers, polyglot | Any | Yes (remote execution) | No | Free (self-host) |

The 80% case: pnpm + Turborepo. pnpm + Nx for 6+ developers. Bazel only for massive polyglot.

## The pnpm workspaces + Turborepo starter

```yaml
# pnpm-workspace.yaml
packages:
  - 'apps/*'
  - 'packages/*'
```

```json
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**"]
    },
    "test": {
      "dependsOn": ["build"],
      "outputs": ["coverage/**"]
    },
    "lint": {},
    "dev": {
      "cache": false,
      "persistent": true
    }
  }
}
```

```json
// package.json (root)
{
  "scripts": {
    "build": "turbo run build",
    "test": "turbo run test",
    "lint": "turbo run lint",
    "dev": "turbo run dev"
  },
  "devDependencies": {
    "turbo": "^2.0.0"
  },
  "packageManager": "pnpm@9.0.0"
}
```

## The pnpm Catalogs unlock

Introduced in pnpm 9.5 (July 2024), Catalogs centralize version specifiers in `pnpm-workspace.yaml`:

```yaml
packages:
  - 'apps/*'
  - 'packages/*'

catalog:
  react: ^18.3.0
  typescript: ^5.5.0
  zod: ^3.23.0
```

Use in any package:

```json
{
  "dependencies": {
    "react": "catalog:",
    "zod": "catalog:"
  }
}
```

All packages reference the catalog version. To upgrade React, edit one line in `pnpm-workspace.yaml`. This is the most underrated monorepo feature of the cycle.

## The 5 layout rules

- **apps/* and packages/*.** Apps never import apps. Packages never import apps. Enforce with `eslint-plugin-import` or `eslint-plugin-boundaries`.
- **TypeScript project references.** Each package has its own `tsconfig.json` with `references` to dependencies. Catches circular imports and unused exports.
- **`tsconfig.base.json` with path aliases.** Centralize compiler options.
- **`workspace:*` protocol.** Internal packages reference each other as `"@myorg/ui": "workspace:*"`. Resolves to the local file.
- **CI runs affected-only with remote cache.** Turborepo's `--filter` or Nx's `--affected` runs only changed packages. Remote cache shares the build across the team.

## The migration pattern

Don't migrate in one PR. Migrate incrementally:

1. Start with two apps and one shared package in a polyrepo structure
2. Add `pnpm-workspace.yaml` referencing existing folders
3. Move shared code into `packages/`
4. Add Turborepo for build orchestration
5. Add Nx generators if needed for scaffolding
6. Add Changesets for versioning if publishing packages

You can always add Turborepo or Nx later; you can't easily undo a 10-package Nx setup you didn't need.

## The when-not-to-monorepo

Monorepos are not free. Costs include:

- Repo size grows with the org
- CI must be scope-aware (affected-only)
- Tooling expertise required (Turborepo, Nx, Bazel)
- Access control granularity is whole-repo, not per-project

For a 2-engineer team with 2 apps and no shared code, polyrepo is fine. The threshold to consider monorepo: 2+ apps sharing code, or 5+ apps regardless of sharing.

## Verification

The tell that the monorepo is working:

- A change to a shared package triggers builds of dependent apps automatically
- CI runs only affected packages; PR builds complete in <5 minutes
- Cross-package refactors are atomic (one commit, one PR)
- Version drift is impossible (one lockfile, one set of catalog versions)
- New engineers onboard with `pnpm install && turbo dev` — no setup instructions

The tell it isn't:

- Each release is a multi-PR coordinated effort
- Types package version 2.0 breaks 3 apps in production
- A new engineer spends a day figuring out which repo to clone first
- Build times scale linearly with repo size

## Gotchas

- **Start small.** Two apps, one shared package. Don't migrate 50 repos in one quarter.
- **pnpm is the 2026 default.** Strict isolation catches dependency bugs that npm and yarn miss.
- **Turborepo's `--filter` is your friend.** Run only the packages a PR touches.
- **Catalogs solve version drift.** Edit one line; every package picks up the upgrade.
- **CI must be scope-aware.** Without affected-only builds, the monorepo is just a slow repo.
- **Apps never import apps.** Enforce with linter; the rule is sacred.
- **Plan the migration, not just the destination.** Tools can be added later; team habits take longer.

## Related

- `worktree/git-rerere.md` — conflict resolution for the monorepo
- `worktree/conventional-commits-2026.md` — clean commit history for versioning
- `worktree/release-please-semantic-release.md` — automated versioning
- `worktree/husky-lint-staged.md` — pre-commit hooks in the monorepo

## Source URLs (verified 2026-08-10)

- https://www.pkgpulse.com/guides/javascript-monorepos-2026-best-practices-pitfalls
- https://toolchew.com/en/best-monorepo-tool/
- https://palakorn.com/blog/monorepo-strategy-pnpm-turbo-nx/
- https://www.digitalapplied.com/blog/monorepo-strategy-2026-turborepo-nx-decision-matrix
- https://turborepo.com/docs
