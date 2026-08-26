# changesets-monorepo-versioning

**Issue:** A pnpm monorepo publishing multiple packages and deploying to
Cloudflare Pages has no versioning discipline — packages are bumped
manually, changelogs are written inconsistently, the mobile app and the
Worker deploy at different semver rhythms, and the Pages deployment
runs unconditionally on every main-branch merge rather than only when
a releasable change is ready.

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

```
# Manual release workflow breaks down:
git log --oneline --since="1 week ago"
  a1b2c3d  fix: session token refresh
  e4f5a6b  chore: update deps
  7c8d9e0  feat: mobile push notifications
  1a2b3c4  fix: typo in README

# No changelog, no version bump, deploy triggered on every push:
pnpm --filter @example project/web deploy   # runs even for chore: commits
```

Package versions in `package.json` are not bumped between releases.
The mobile app's `app.json` version is updated by hand and often
forgotten. There is no automated record of what changed between
deployed versions of the Cloudflare Worker or Pages site.

## Context

Changesets is a versioning and changelog tool built for pnpm/npm/yarn
workspaces. Contributors add a "changeset" file (a small YAML-frontmatter
Markdown file) when they open a pull request; the changeset describes
which packages are affected and whether the change is `major`, `minor`,
or `patch`. A CI job periodically opens a "Version PR" that accumulates
all pending changesets into version bumps and `CHANGELOG.md` entries.
Merging the Version PR triggers the actual publish/deploy pipeline.

For example project, Changesets drives three release tracks:
1. **npm packages** (`packages/shared`, `packages/ui`) — published to npm or
   a private registry.
2. **Cloudflare Workers + Pages** (`apps/worker`, `apps/web`) — deployed
   via `wrangler deploy` / `wrangler pages deploy`.
3. **Mobile app** (`apps/mobile`) — `app.json` version bumped, OTA update
   pushed via EAS Update or a version tag triggers a new native build.

## Installation

```bash
pnpm add -D -w @changesets/cli
pnpm changeset init
```

This creates `.changeset/config.json` and `.changeset/README.md`.

## .changeset/config.json

```json
{
  "$schema": "https://unpkg.com/@changesets/config/schema.json",
  "changelog": "@changesets/changelog-github",
  "commit": false,
  "fixed": [],
  "linked": [
    ["@example project/worker", "@example project/web"]
  ],
  "access": "restricted",
  "baseBranch": "main",
  "updateInternalDependencies": "patch",
  "ignore": ["@example project/mobile"]
}
```

Key decisions:
- `"linked": [["@example project/worker", "@example project/web"]]` — Worker and web app
  always share the same version number; a patch to the Worker bumps
  both to the same new version.
- `"ignore": ["@example project/mobile"]` — the mobile app has its own version
  cadence managed outside Changesets (see below).
- `"commit": false` — the Version PR workflow (not individual commits)
  applies version bumps.
- `"updateInternalDependencies": "patch"` — when `packages/shared`
  is bumped, all consumers (`apps/worker`, `apps/web`) get their
  `package.json` dependency updated automatically.

## GitHub Changelog package

```bash
pnpm add -D -w @changesets/changelog-github
```

Requires `GITHUB_TOKEN` in CI to resolve PR titles and authors into
changelog entries.

## Developer workflow — adding a changeset

```bash
# After implementing a feature branch
pnpm changeset

# Interactive prompt:
#  Which packages are affected? → @example project/worker
#  Bump type? → minor
#  Summary: add rate-limit middleware using Cloudflare's RateLimit API

# Creates: .changeset/lucky-dogs-fly.md
```

```markdown
---
"@example project/worker": minor
---

Add rate-limit middleware using Cloudflare's RateLimit binding.
Requests exceeding 100 req/min per IP receive a 429 response.
```

Commit the changeset file with the PR. Multiple changesets accumulate
until the Version PR is merged.

## Version PR automation (GitHub Actions)

```yaml
# .github/workflows/version-or-publish.yml
name: Version or Publish

on:
  push:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  version-or-publish:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Create Version PR or Publish
        id: changesets
        uses: changesets/action@v1
        with:
          publish: pnpm run release
          version: pnpm run version
          commit: "chore: release"
          title: "chore: release"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ vars.CLOUDFLARE_ACCOUNT_ID }}

      - name: Deploy to Cloudflare Pages (on publish)
        if: steps.changesets.outputs.published == 'true'
        run: pnpm --filter @example project/web exec wrangler pages deploy .next/
```

`steps.changesets.outputs.published == 'true'` is the key gate —
Cloudflare Pages deploy runs only when Changesets actually published
new versions, not on every push to main.

## Package scripts

```json
// package.json (root)
{
  "scripts": {
    "version":    "changeset version && pnpm install --lockfile-only",
    "release":    "changeset publish",
    "changeset":  "changeset"
  }
}
```

`pnpm install --lockfile-only` after `changeset version` updates
`pnpm-lock.yaml` to reflect the new internal dependency versions
without re-installing.

## Cloudflare Pages deploy on release

```json
// apps/web/package.json
{
  "scripts": {
    "build":   "next build",
    "release": "wrangler pages deploy .next/ --project-name=example project-web --commit-dirty=false"
  }
}
```

```json
// apps/worker/package.json
{
  "scripts": {
    "release": "wrangler deploy --env production"
  }
}
```

The root `release` script calls `changeset publish`, which executes
each package's `release` script in topological order after bumping
`package.json` versions.

## Mobile app version bump

The mobile app (`apps/mobile`, Expo) is excluded from Changesets but
needs its `app.json` version kept in sync with the overall release.

```bash
# scripts/bump-mobile-version.mjs
import { readFileSync, writeFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync("apps/worker/package.json", "utf8"));
const appJson = JSON.parse(readFileSync("apps/mobile/app.json", "utf8"));

appJson.expo.version = pkg.version;
// Increment build number monotonically
appJson.expo.ios.buildNumber = String(
  Number(appJson.expo.ios.buildNumber) + 1
);
appJson.expo.android.versionCode += 1;

writeFileSync("apps/mobile/app.json", JSON.stringify(appJson, null, 2) + "\n");
console.log(`Mobile bumped to ${pkg.version}`);
```

Add to the root `version` script:

```json
{
  "scripts": {
    "version": "changeset version && node scripts/bump-mobile-version.mjs && pnpm install --lockfile-only"
  }
}
```

## Viewing pending changesets

```bash
# List accumulated changesets not yet in a Version PR
pnpm changeset status

# Preview what the next version bump would be
pnpm changeset status --verbose
```

## Anti-patterns

- **Merging without a changeset on feature PRs** — the Version PR will
  never open for that PR's changes; use a branch protection rule or a
  GitHub Action that checks for a changeset file on non-chore PRs.
- **Running `wrangler deploy` on every push to main** — defeats the
  purpose of Changesets; gate it on `changesets.outputs.published`.
- **Using `"commit": true`** in config — creates a commit per changeset
  apply, polluting `git log`; prefer the Version PR workflow.
- **Bumping `apps/mobile` via Changesets** — Expo's native build system
  has different versioning semantics; manage it via a separate script
  triggered by the version step.

## Gotchas

- `changeset publish` calls `npm publish` by default; for Cloudflare
  deployments override the `release` script in each app's `package.json`.
- The `linked` array means a minor bump to `@example project/worker` also bumps
  `@example project/web` to a minor even if only a patch changed in the web app.
- `@changesets/changelog-github` requires `GITHUB_TOKEN` at version-PR
  creation time, not just at publish time.
- If `pnpm-lock.yaml` is not committed after `changeset version`, pnpm CI
  may fail with a lockfile mismatch on the Version PR's commit.

## Verification

```bash
# Dry-run the version step locally
pnpm changeset version
git diff --stat   # should show package.json + CHANGELOG.md changes

# Preview publish (does not actually publish)
pnpm changeset publish --dry-run

# Confirm Pages deploy fires on publish output
# Check GitHub Actions run: step "Create Version PR or Publish"
# outputs.published should be "true" after merging the Version PR
```

## Related

- `documentation/docs/policies/devtools/changesets-versioning.md`
- `documentation/docs/policies/devtools/changeset-versioning-monorepo-release.md`
- `documentation/docs/policies/devtools/turborepo-cloudflare-workers-pipeline.md`
- `documentation/docs/policies/devtools/pnpm-workspace-setup.md`
- `documentation/docs/policies/devtools/semantic-release-setup.md`

## Sources

- https://github.com/changesets/changesets
- https://github.com/changesets/action
- https://pnpm.io/using-changesets
- https://developers.cloudflare.com/pages/how-to/deploy-via-wrangler/
- https://docs.expo.dev/eas-update/introduction/
