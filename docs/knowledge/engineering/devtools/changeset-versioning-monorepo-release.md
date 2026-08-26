# Changesets Monorepo Versioning, CHANGELOG Generation, and Wrangler Release Deploy

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

In a Next.js + Cloudflare Workers monorepo, coordinating package version bumps,
CHANGELOG entries, npm publishes, and Wrangler production deploys across multiple
packages manually is error-prone and inconsistent. A release of the worker might
ship without a matching version bump in the shared library, or a CHANGELOG entry
is forgotten under time pressure.

## Context

example project (example.com) uses Changesets (`@changesets/cli`) to manage semantic version
bumps across all packages in the pnpm workspace. The workflow is:

1. Developer opens a PR and adds a changeset file describing the change.
2. A CI bot (the Changesets GitHub Action) aggregates open changeset files into a
   "Version Packages" PR.
3. Merging the Version PR triggers versioning, CHANGELOG generation, npm package
   publishing (for shared libs), and a Wrangler deploy of the Worker.

Key packages in the example project workspace:

| Package              | npm publish | Wrangler deploy |
|----------------------|-------------|-----------------|
| `@example project/shared`       | yes         | no              |
| `@example project/ui`           | yes         | no              |
| `@example project/worker`       | no          | yes             |
| `apps/web` (Next.js) | no          | no (Vercel CI)  |

## Installation

```bash
pnpm add -Dw @changesets/cli
pnpm changeset init
```

This creates `.changeset/config.json` and `.changeset/README.md` at the workspace root.

### .changeset/config.json

```json
{
  "$schema": "https://unpkg.com/@changesets/config@3.0.0/schema.json",
  "changelog": "@changesets/cli/changelog",
  "commit": false,
  "fixed": [],
  "linked": [],
  "access": "public",
  "baseBranch": "main",
  "updateInternalDependencies": "patch",
  "ignore": ["apps/web", "@example project/worker"],
  "snapshot": {
    "useCalculatedVersion": true,
    "prereleaseTemplate": null
  }
}
```

`ignore` lists packages that changesets should not version or publish. The Worker is
ignored from changeset versioning because it is deployed by Wrangler, not published
to npm. `apps/web` is ignored because Vercel handles its deployments.

## Adding a Changeset

Every PR that changes observable behaviour must include a changeset file. The
developer runs:

```bash
pnpm changeset
```

The interactive CLI asks:
1. Which packages are affected? (select from workspace list)
2. What is the bump type? (major / minor / patch)
3. What is the summary? (becomes the CHANGELOG entry)

This writes a file like `.changeset/fuzzy-lions-dance.md`:

```markdown
---
"@example project/shared": minor
---

Add `parseWebhookPayload` utility that validates HMAC signatures from Stripe webhooks.
```

Commit the changeset file alongside the code change. One changeset per logical change;
multiple packages can be bumped in a single changeset file.

## Version Packages PR (Changesets Bot)

The Changesets GitHub Action opens a PR titled "Version Packages" that:
- Aggregates all pending changeset files
- Bumps `version` fields in `package.json` files
- Updates `CHANGELOG.md` in each affected package
- Deletes the consumed changeset files

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    branches: [main]

concurrency: ${{ github.workflow }}-${{ github.ref }}

permissions:
  contents: write
  pull-requests: write
  id-token: write   # for npm provenance

jobs:
  release:
    name: Release
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
          registry-url: https://registry.npmjs.org

      - run: pnpm install --frozen-lockfile

      - name: Create Release Pull Request or Publish
        id: changesets
        uses: changesets/action@v1
        with:
          publish: pnpm release
          title: "chore: version packages"
          commit: "chore: version packages"
          createGithubReleases: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
          NPM_CONFIG_PROVENANCE: "true"
```

`pnpm release` is defined in the root `package.json`:

```json
{
  "scripts": {
    "release": "pnpm build && changeset publish"
  }
}
```

## Wrangler Deploy on Release Tag

When `createGithubReleases: true`, the Changesets action creates a GitHub Release and
tag for each published package (e.g. `@example project/shared@1.4.0`). A separate workflow
deploys the Worker when any release tag is pushed that affects it.

Since the Worker is not versioned by Changesets, the deploy trigger is a push to `main`
after the Version PR merges — or a dedicated release tag convention.

### Worker deploy workflow

```yaml
# .github/workflows/worker-deploy.yml
name: Deploy Worker

on:
  push:
    branches: [main]
    paths:
      - "packages/worker/**"
      - "packages/shared/**"   # worker depends on shared

jobs:
  deploy:
    name: Wrangler deploy
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Build shared
        run: pnpm --filter @example project/shared build

      - name: Deploy Worker
        working-directory: packages/worker
        run: pnpm wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

`paths` restricts the deploy trigger: if only `apps/web` changes, the Worker is not
redeployed unnecessarily.

## pnpm Workspace Publish Order

`changeset publish` respects the dependency graph in the workspace when determining
publish order. If `@example project/ui` depends on `@example project/shared`, shared is always published
first.

```
pnpm workspace publish order (automatic):
  1. @example project/shared        (no internal deps)
  2. @example project/ui            (depends on @example project/shared)
```

### Verifying the publish order

```bash
# Dry-run to see what would be published and in what order
pnpm changeset publish --dry-run
```

## CHANGELOG Format

Each package's `CHANGELOG.md` is automatically maintained. Example:

```markdown
# @example project/shared

## 1.4.0

### Minor Changes

- a1b2c3d: Add `parseWebhookPayload` utility that validates HMAC signatures
  from Stripe webhooks.

## 1.3.1

### Patch Changes

- f9e8d7c: Fix edge case in `signJwt` when `exp` is exactly 0.
```

The hash prefix links to the commit in the GitHub release view.

## Pre-release Snapshots

For testing a release candidate on the Worker staging environment before merging:

```bash
# Enter pre-release mode
pnpm changeset pre enter next

# Add a changeset as normal, then version
pnpm changeset version
# Bumps to 1.4.0-next.0

# Publish snapshot to npm with dist-tag
pnpm changeset publish --tag next

# Exit pre-release mode when ready for stable
pnpm changeset pre exit
```

## Anti-patterns

- **Manually editing `CHANGELOG.md`**: Changesets owns this file. Hand-editing causes
  merge conflicts when the bot next runs. Write the summary in the changeset file instead.
- **Bumping `package.json` version by hand**: version fields are managed by
  `changeset version`. Manual bumps are overwritten when the Version PR merges.
- **Including `apps/web` in changeset scopes**: the web app is deployed by Vercel on
  every push to main; it does not need a version bump or CHANGELOG entry.
- **Deploying the Worker from the changeset publish script**: the Worker is not an npm
  package. Wrangler deploys belong in a separate workflow triggered by path changes,
  not inside the changeset publish flow.
- **Skipping the changeset file in a PR**: CI should enforce that every PR touching
  `packages/` contains a changeset. Use the `changeset-bot` GitHub App for this check.

## Gotchas

- **`updateInternalDependencies: "patch"`**: when `@example project/ui` depends on `@example project/shared`
  and shared gets a minor bump, ui's dependency is only bumped as a patch. Set to
  `"minor"` if you want internal dep bumps to flow through as minor.
- **`commit: false` prevents auto-commit by the CLI**: the Changesets action handles
  commits. Setting `commit: true` creates a double-commit in the Version PR.
- **GitHub Releases are one-per-package**: with multiple packages publishing in one
  run, the Changesets action creates one GitHub Release per package. The list on the
  repo releases page can grow quickly.
- **`createGithubReleases` requires `contents: write` permission**: without it the
  action silently skips the GitHub Release creation without failing the workflow.

## Verification

```bash
# 1. Confirm changeset CLI is available
pnpm changeset --version
# Expected: x.y.z

# 2. List pending changesets
pnpm changeset status
# Expected: lists packages with pending bumps, or "No changesets found"

# 3. Dry-run version bump
pnpm changeset version --dry-run
# Expected: shows what package.json changes would be made

# 4. Dry-run publish (does not actually publish)
pnpm changeset publish --dry-run
# Expected: lists packages that would be published in dependency order

# 5. Confirm CHANGELOG was updated after versioning
git diff CHANGELOG.md
# Expected: new version section added
```

## Related

- `semantic-release-setup.md` — alternative release automation tool
- `pnpm-workspace-setup.md` — pnpm workspace configuration
- `turborepo-cloudflare-workers-pipeline.md` — build pipeline for the monorepo
- `wrangler-dev-local-d1-r2-testing.md` — local Worker development before release
- `npm-trusted-publishing-oidc-release-boundaries.md` — OIDC-based npm publish

## Sources

- https://github.com/changesets/changesets/blob/main/docs/intro-to-using-changesets.md
- https://github.com/changesets/changesets/blob/main/docs/config-file-options.md
- https://github.com/changesets/action
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://pnpm.io/workspaces
