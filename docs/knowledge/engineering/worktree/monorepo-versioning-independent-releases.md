# Monorepo Versioning and Independent Releases

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your monorepo contains multiple packages with different consumers and
release cadences, but you version and release them all together. A patch
to the CLI tool forces a release of the unrelated UI library. Consumers
cannot pin stable versions of individual packages, and your changelog is
a single file mixing unrelated changes.

## Context

Monorepo versioning strategies fall into two categories: **fixed** (all
packages share one version and release together) and **independent** (each
package has its own version and releases when it changes). The choice
depends on how tightly coupled the packages are and whether they serve
different consumers. In 2026, Changesets + pnpm is the dominant pattern
for independent versioning in the npm ecosystem, with Turborepo or Nx
handling task orchestration.

## Versioning strategies

### Fixed versioning

All packages share the same version number and release as a unit.

- **Best for:** tightly coupled packages that always ship together (e.g.,
  `@mylib/core`, `@mylib/react`, `@mylib/vue` where all must be on the
  same version).
- **Tools:** Lerna (fixed mode), changesets (fixed mode).
- **Tradeoff:** simple to understand, but forces unnecessary releases and
  version bumps for unchanged packages.

### Independent versioning

Each package has its own version and releases independently when it
changes.

- **Best for:** packages with different consumers and release cadences
  (e.g., a CLI tool and a UI library in the same repo).
- **Tools:** Changesets (independent mode), semantic-release, release-it.
- **Tradeoff:** more complex release process, requires dependency version
  coordination between internal packages.

## Changesets workflow (recommended for 2026)

Changesets is the recommended tool for independent versioning in pnpm
monorepos. The changeset-file model integrates cleanly with PR-based
workflows.

### 1. Developer adds a changeset in the PR

```bash
pnpm changeset
# Interactive prompt:
# Which packages changed? @myapp/cli
# What type of change? patch
# Summary: Fix argument parsing for --config flag
```

This creates a `.changeset/cool-dogs-fly.md` file:

```markdown
---
"@myapp/cli": patch
---

Fix argument parsing for --config flag
```

### 2. CI validates changeset presence

```yaml
# .github/workflows/changeset-check.yml
- name: Check for changeset
  run: pnpm changeset status
  # Fails if the PR changes packages but has no changeset file
```

### 3. Changesets bot opens a "Version Packages" PR

When changesets accumulate on main, the Changesets GitHub Action opens a
PR that:

- Bumps version numbers in each changed package's `package.json`.
- Updates `CHANGELOG.md` for each package.
- Removes consumed `.changeset/*.md` files.

### 4. Merge the Version PR to publish

```yaml
# .github/workflows/release.yml
- name: Publish packages
  run: pnpm changeset publish
  env:
    NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
```

## Turborepo integration

Turborepo handles task orchestration (build, test, lint) with dependency-
aware caching. Combined with changesets for versioning:

```json
// turbo.json
{
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**"]
    },
    "test": {
      "dependsOn": ["build"]
    }
  }
}
```

### OIDC publishing (2026 best practice)

Changesets + OIDC is the default publishing pattern in 2026. Use npm's
provenance-enabled publishing with GitHub Actions OIDC tokens — no
long-lived NPM_TOKEN needed.

```yaml
permissions:
  id-token: write
  contents: write

- run: pnpm changeset publish
  env:
    NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
    NPM_CONFIG_PROVENANCE: true
```

## Alternatives comparison

| Tool | Versioning model | Commit convention required | Monorepo support |
|---|---|---|---|
| **Changesets** | Explicit changeset files | No | Excellent (pnpm, npm, yarn) |
| **semantic-release** | Commit message convention | Yes (Conventional Commits) | Via plugins (multi-release) |
| **release-it** | Interactive or CI-driven | Optional | Limited (single-package focus) |
| **Lerna** | Fixed or independent | Optional | Good but largely superseded |

## Anti-patterns

- **No changesets for internal packages** — even packages not published
  to npm benefit from changelogs. Use changesets for internal packages
  to maintain a change history.
- **Skipping the Version PR review** — the Version PR is your last chance
  to catch incorrect version bumps. A patch that should be a major is a
  breaking change for consumers.
- **Manual version bumps** — editing `package.json` versions by hand
  bypasses changelog generation and risks inconsistency.
- **Publishing all packages on every merge** — without changesets, every
  merge publishes all packages regardless of whether they changed. This
  floods consumers with no-op updates.

## Gotchas

- **Internal dependency version ranges** — when package A depends on
  package B (both in the monorepo), changesets automatically bumps A
  when B gets a version bump, but only if A declares a version range
  that the new B version satisfies. Use `workspace:*` in development
  and let changesets resolve to actual versions at publish time.
- **Pre-release workflow** — changesets supports pre-release mode
  (`pnpm changeset pre enter beta`), but pre-release management adds
  complexity. Keep it simple for most projects.
- **pnpm catalogs** — pnpm 9's `catalogs` feature lets you define shared
  dependency versions in `pnpm-workspace.yaml`. Works well with
  changesets but requires all team members to use the catalog.
- **Turborepo remote cache** — Turborepo's remote cache (Vercel or self-
  hosted) dramatically speeds up CI for monorepos but requires careful
  cache key configuration to avoid stale builds.

## Verification

- Every PR that changes a package includes a changeset file.
- CI validates changeset presence on PRs.
- Changelogs are generated per package, not per repo.
- Published packages include npm provenance attestation.
- Version bumps are reviewed via the Version Packages PR.
- Internal dependency versions resolve correctly at publish time.

## Related

- `documentation/docs/policies/worktree/conventional-commits.md`
- `documentation/docs/policies/worktree/monorepo-tooling.md`
- `documentation/docs/policies/deploy/semantic-versioning.md`

## Source URLs (verified 2026-08-16)

- Changesets documentation — https://github.com/changesets/changesets
- Turborepo documentation — https://turbo.build/repo/docs
- Monorepo setup guide — https://chenguangliang.com/en/posts/blog193_monorepo-practice-from-zero-to-production/
- semantic-release vs changesets comparison — https://www.pkgpulse.com/guides/semantic-release-vs-changesets-vs-release-it-release-2026
