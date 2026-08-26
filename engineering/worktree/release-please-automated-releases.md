# Automated Releases with Release Please

**Author:** example.com
**Project:** example project (example.com) — pnpm monorepo, Cloudflare Workers + Pages
**Last updated:** 2026-08-22

---

## Overview

Release Please is a Google-maintained GitHub Action that automates the full release lifecycle based on Conventional Commits. Every time a `feat`, `fix`, or `BREAKING CHANGE` commit lands on `main`, Release Please opens or updates a Release PR that bumps the version, updates `CHANGELOG.md`, and pins the tag. When the team merges that PR, Release Please creates the GitHub Release and the tag — which then triggers the production Wrangler deploy.

This article explains how to configure Release Please for example project's pnpm monorepo, generate per-package changelogs, and wire the release tag to a Cloudflare Workers version tagging workflow.

---

## How Release Please Works

1. **Scan commits** — after each push to `main`, Release Please inspects new commits since the last release tag using the Conventional Commits spec.
2. **Open/update a Release PR** — it creates or amends a PR titled `chore(release): <package> <version>` with a bumped version file and updated changelog.
3. **Merge triggers the release** — when the Release PR is merged, Release Please creates a GitHub Release + tag, which downstream workflows can use as a deploy trigger.

This means the team controls _when_ a release ships (by merging the Release PR) while Release Please automates _what_ the release contains.

---

## GitHub Action Setup

```yaml
# .github/workflows/release-please.yml
name: Release Please

on:
  push:
    branches: [main]

permissions:
  contents: write        # create tags and releases
  pull-requests: write   # open and update Release PRs

jobs:
  release-please:
    name: Release Please
    runs-on: ubuntu-latest

    outputs:
      # Expose release outputs for downstream jobs
      api_worker_released: ${{ steps.rp.outputs['packages/api-worker--release_created'] }}
      api_worker_tag:      ${{ steps.rp.outputs['packages/api-worker--tag_name'] }}
      web_released:        ${{ steps.rp.outputs['packages/web--release_created'] }}
      web_tag:             ${{ steps.rp.outputs['packages/web--tag_name'] }}

    steps:
      - uses: googleapis/release-please-action@v4
        id: rp
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          config-file: release-please-config.json
          manifest-file: .release-please-manifest.json

  # ── Deploy the Worker if a release was created ───────────────────────────
  deploy-api-worker:
    name: Deploy API Worker
    needs: release-please
    if: needs.release-please.outputs.api_worker_released == 'true'
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ needs.release-please.outputs.api_worker_tag }}

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Build
        run: pnpm --filter api-worker build

      - name: Deploy to Cloudflare Workers (production)
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          workingDirectory: packages/api-worker
          command: deploy --env production

      - name: Tag Cloudflare Workers deployment
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          workingDirectory: packages/api-worker
          command: >
            deployments create
            --tag=${{ needs.release-please.outputs.api_worker_tag }}
            --message="Release ${{ needs.release-please.outputs.api_worker_tag }}"
```

---

## Monorepo Configuration

### release-please-config.json

This file tells Release Please which packages exist, their versioning strategy, and where their changelogs live.

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "release-type": "node",
  "bump-minor-pre-major": true,
  "bump-patch-for-minor-pre-major": true,
  "changelog-sections": [
    { "type": "feat",     "section": "Features" },
    { "type": "fix",      "section": "Bug Fixes" },
    { "type": "perf",     "section": "Performance" },
    { "type": "revert",   "section": "Reverts" },
    { "type": "docs",     "section": "Documentation", "hidden": false },
    { "type": "ci",       "section": "CI/CD",          "hidden": true },
    { "type": "chore",    "section": "Miscellaneous",  "hidden": true }
  ],
  "packages": {
    "packages/api-worker": {
      "release-type": "node",
      "package-name": "@example project/api-worker",
      "changelog-path": "CHANGELOG.md",
      "versioning": "semver"
    },
    "packages/web": {
      "release-type": "node",
      "package-name": "@example project/web",
      "changelog-path": "CHANGELOG.md"
    },
    "packages/shared": {
      "release-type": "node",
      "package-name": "@example project/shared",
      "changelog-path": "CHANGELOG.md"
    },
    "apps/mobile": {
      "release-type": "node",
      "package-name": "@example project/mobile",
      "changelog-path": "CHANGELOG.md",
      "bump-minor-pre-major": false
    }
  }
}
```

### .release-please-manifest.json

Tracks the current version for each package. Release Please reads and writes this file automatically — do not edit it by hand except during initial setup.

```json
{
  "packages/api-worker": "1.4.2",
  "packages/web": "1.4.2",
  "packages/shared": "1.3.0",
  "apps/mobile": "2.4.1"
}
```

---

## Conventional Commits → Version Bumps

Release Please maps commit types to semantic version bumps:

| Commit prefix | Version bump | Example |
|---------------|-------------|---------|
| `fix(api):` | patch (1.4.2 → 1.4.3) | `fix(api): handle missing auth header` |
| `feat(workers):` | minor (1.4.2 → 1.5.0) | `feat(workers): add webhook signing` |
| `BREAKING CHANGE:` in footer | major (1.4.2 → 2.0.0) | `feat(api)!: remove v1 endpoints` |
| `chore:`, `ci:`, `docs:` | no bump | `chore(deps): update wrangler` |

For the `!` shorthand breaking change syntax to work, commitlint must allow it. The `@commitlint/config-conventional` preset handles this by default.

---

## Cloudflare Workers Version Tagging

Cloudflare Workers supports named version annotations on deployments, separate from the GitHub release tag. Use Wrangler's `deployments` API to attach the Release Please tag to the Workers deployment:

```bash
# Called from the deploy job above:
wrangler deployments create \
  --tag="packages/api-worker@1.5.0" \
  --message="Release packages/api-worker@1.5.0 — adds webhook signing"
```

This creates an audit trail in the Cloudflare dashboard: each production deployment is linked to a specific GitHub release tag, making rollbacks trivial — you pick a previous deployment from the list and promote it.

### Rollback to a prior Workers version

```bash
# List deployments
wrangler deployments list --env production

# Rollback to a specific deployment ID
wrangler rollback <deployment-id> --env production --message="Rollback to 1.4.2 — 1.5.0 regression"
```

---

## Generated CHANGELOG Format

After a release, `packages/api-worker/CHANGELOG.md` looks like:

```markdown
# Changelog

## [1.5.0](https://github.com/org/example project/compare/packages/api-worker@1.4.2...packages/api-worker@1.5.0) (2026-08-22)

### Features

* **workers:** add webhook HMAC-SHA256 signature validation ([#241](https://github.com/org/example project/pull/241)) ([a3f9c12](https://github.com/org/example project/commit/a3f9c12))
* **api:** expose /v1/features endpoint for mobile flag sync ([#238](https://github.com/org/example project/pull/238)) ([b7d1e88](https://github.com/org/example project/commit/b7d1e88))

### Bug Fixes

* **workers:** handle KV timeout with 503 instead of 500 ([#240](https://github.com/org/example project/pull/240)) ([c2a4f01](https://github.com/org/example project/commit/c2a4f01))
```

Each entry links to the PR and commit, so reviewers and users can trace every change.

---

## Release PR Example

When Release Please creates the Release PR, it looks like:

```
Title: chore(release): release packages/api-worker 1.5.0

Files changed:
  packages/api-worker/package.json        version: "1.4.2" → "1.5.0"
  packages/api-worker/CHANGELOG.md        new section prepended
  .release-please-manifest.json           "packages/api-worker": "1.5.0"
```

The Release PR is controlled by a bot label (`autorelease: pending`). Additional commits pushed to `main` after the PR opens cause Release Please to amend the PR — it accumulates changes until the team decides to release by merging.

---

## Multi-Package Releases and Dependencies

When `packages/shared` releases a new version and `packages/api-worker` depends on it, Release Please does not automatically cascade the version bump. The team must update the version reference in `api-worker/package.json` manually or via Renovate (see the Renovate article). Release Please will then include that change in the next `api-worker` Release PR.

---

## Bootstrapping an Existing Repository

If the repository already has versions but no Release Please manifest:

```bash
# Install the CLI
pnpm add -D -w release-please

# Bootstrap — writes .release-please-manifest.json from current package.json versions
pnpm exec release-please bootstrap \
  --token=$GITHUB_TOKEN \
  --repo-url=org/example project \
  --release-type=node \
  --manifest-file=.release-please-manifest.json \
  --config-file=release-please-config.json
```

---

## Summary

- Release Please reads Conventional Commits from `main` and creates Release PRs automatically.
- `release-please-config.json` defines all monorepo packages and their changelog format.
- Merging a Release PR creates a GitHub Release + tag, which triggers the Wrangler deploy.
- Cloudflare Workers deployment version tagging links each release to its deployment for easy rollback.
- The generated changelog is fully automatic — no human-written release notes required.

**References**
- Release Please: https://github.com/googleapis/release-please
- `googleapis/release-please-action`: https://github.com/googleapis/release-please-action
- Wrangler Deployments: https://developers.cloudflare.com/workers/wrangler/commands/#deployments
