# conventional-commits-monorepo-changesets-2026

**Issue:** A monorepo publishes 12 packages. A team wants to release only the 3 that changed. Conventional Commits says "feat: ..." triggers a version bump — but which package? Changesets declares per-package changes explicitly.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

In a monorepo, `feat(api): add user endpoint` and `feat(ui): add button` both look like "feat" — but they affect different packages with different version histories. Conventional Commits doesn't know package boundaries; it derives one version from the commit graph. A monorepo with multiple published packages needs per-package versioning.

## Root cause

Changesets is a per-package versioning tool designed for monorepos. The developer writes a `.changeset/<random-id>.md` file per change, declaring which packages are affected and how. The release tooling aggregates the changesets, bumps versions, and generates changelogs per package.

## The Changesets workflow

```bash
# 1. Developer creates a changeset for their change
npx changeset
# ? Which packages would you like to include? » @myorg/api
# ? What kind of change is this for @myorg/api? » minor
# ? Please write a summary for this change » add user preferences endpoint
# → Creates .changeset/abc123.md
```

```markdown
---
"@myorg/api": minor
---

Add user preferences endpoint
```

The file is committed alongside the change. CI runs `npx changeset status` to verify the changeset exists.

## The version-derivation model

Unlike Conventional Commits (which derives version from commit type), Changesets:

1. Aggregates all changesets in `.changeset/` (the "pending" set)
2. Determines the highest bump type per package across all pending changesets
3. Bumps the version accordingly: `patch` (0.0.x), `minor` (0.x.0), `major` (x.0.0)
4. Generates a CHANGELOG.md entry per package
5. Deletes the consumed changesets

A PR that includes a changeset triggers a "Version Packages" PR (via the Changesets GitHub Action) once merged. That PR contains the version bumps and changelogs. Merging the Version Packages PR publishes the packages.

## The combined commit + changesets pattern

Both can coexist:

- **Conventional Commits** for the commit history (clean, parseable, drives `git log` tooling)
- **Changesets** for the release notes and per-package version bumps

The commit message follows Conventional Commits; the changeset is a separate file that declares the per-package impact. CI runs both: `commitlint` on the commit, `changeset status` on the changeset.

## The 5 commands

```bash
# Create a changeset
npx changeset

# Status (check what would be released)
npx changeset status

# Version (consume changesets, bump versions, generate changelogs)
npx changeset version

# Publish
npx changeset publish

# Pre-enter a release (skip the version PR)
npx changeset version --snapshot
```

## The package.json wiring

For each published package:

```json
{
  "name": "@myorg/api",
  "version": "1.2.3",
  "scripts": {
    "version": "changeset version",
    "release": "npm run build && changeset publish"
  }
}
```

For the monorepo root:

```json
{
  "scripts": {
    "version": "changeset version",
    "release": "pnpm -r --filter \"./packages/*\" run build && changeset publish"
  }
}
```

## The fixed vs flexible groups

Changesets supports "fixed" groups: a set of packages that always version together. Useful for tightly coupled packages:

```json
// .changeset/config.json
{
  "fixed": [["@myorg/api", "@myorg/api-types"]],
  "linked": [["@myorg/web", "@myorg/mobile"]]
}
```

- `fixed`: all packages in the group bump to the same version
- `linked`: all packages in the group bump together (e.g., always at the same release time) but can have different versions

For most monorepos, the default (independent versioning per package) is correct. Use `fixed` only when packages are published together as a unit.

## The CI integration

```yaml
# .github/workflows/changesets.yml
name: Changesets
on:
  pull_request:
    paths:
      - '.changeset/**'
      - 'packages/**'

jobs:
  changesets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: changesets/action@v1
        with:
          command: ci
```

`changesets/action` runs `changeset status` on PRs. It comments on the PR with a summary of pending changes and the version that would be published. It also creates a "Version Packages" PR when changes are merged to main.

## The 5 best practices

1. **One changeset per change.** Don't batch multiple unrelated changes into one changeset.
2. **Use the package's actual scope.** `@myorg/api` not "the API" — name the package as published.
3. **Be specific in the summary.** "Add user preferences endpoint" not "updates".
4. **Run `changeset status` in CI.** A PR without a changeset for a public-package change fails.
5. **Let the Version Packages PR be reviewed.** The version bump is part of the release, not a CI step.

## The combined with release-please alternative

Some teams use `release-please` (Google) which uses Conventional Commits to drive versioning. In a monorepo, `release-please` works but doesn't natively support per-package versioning. Changesets is the better fit for monorepos with multiple published packages; `release-please` is the better fit for single-package or "all packages version together" repos.

## Verification

The tell that changesets is working:

- Each PR that affects a published package includes a `.changeset/*.md` file
- CI comments on the PR with the pending version and changelog
- A "Version Packages" PR is created on merge, showing all pending version bumps
- Each published package has a `CHANGELOG.md` generated from the changesets
- The version-bump audit trail is clear: which commit, which changeset, which package

The tell it isn't:

- PRs are merged without changesets; release tooling doesn't know what to publish
- Manual version bumps in `package.json`
- One CHANGELOG.md for the whole monorepo (defeats per-package versioning)
- "We forgot to add a changeset" is a routine occurrence

## Gotchas

- **One changeset per change, not per PR.** A PR can include multiple changesets if it touches multiple packages with independent changes.
- **The version PR is the audit trail.** Review it like any other PR; don't auto-merge.
- **Fixed groups are for tightly coupled packages.** Don't use them by default.
- **Snapshot releases for testing.** `changeset version --snapshot` creates a temporary version for canary testing without affecting the real release.
- **Bump type precedence: major > minor > patch.** A package with both `minor` and `patch` changesets bumps to `minor`.
- **The first release is a one-time setup.** Initialize each package with `0.0.0` or `1.0.0`; subsequent releases derive from changesets.

## Related

- `worktree/conventional-commits-2026.md` — the commit message convention
- `worktree/release-please-semantic-release.md` — single-package alternative
- `worktree/monorepo-pnpm-turborepo-2026.md` — the monorepo context
- `worktree/husky-lint-staged.md` — local pre-commit gates

## Source URLs (verified 2026-08-10)

- https://github.com/changesets/changesets
- https://github.com/changesets/action
- https://turbo.build/docs/handbook/publishing-packages/versioning
- https://www.pnpm.io/inject-versions
- https://latchkey.dev/learn/tool-comparisons/semantic-release-vs-release-please
