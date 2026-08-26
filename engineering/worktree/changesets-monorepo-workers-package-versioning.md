# Changesets for Versioning Workers Packages in a Monorepo

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your monorepo contains several Cloudflare Worker packages under `packages/`. Contributors open PRs but version bumps and changelogs are done manually, leading to inconsistent semver, missing release notes, and all Workers being redeployed on every merge even when only one changed. You want a pull-request-driven versioning workflow that produces accurate `CHANGELOG.md` files and triggers targeted `wrangler deploy` calls.

## Context

[Changesets](https://github.com/changesets/changesets) is a tool designed for monorepos. Each PR contributor drops a small Markdown "changeset" file describing what changed and at what semver level. On merge, a GitHub Actions release workflow calls `changeset version` (bumps `package.json` versions and writes changelogs) and `changeset publish` (tags the release). A second step then deploys only the Workers whose `package.json` version actually changed.

---

## Full Setup: Config, Workflow, and Deploy Step

```jsonc
// .changeset/config.json
{
  "$schema": "https://unpkg.com/@changesets/config@3.0.0/schema.json",
  "changelog": "@changesets/cli/changelog",
  "commit": false,
  "fixed": [],
  "linked": [],
  "access": "restricted",
  "baseBranch": "main",
  "updateInternalDependencies": "patch",
  "ignore": []
}
```

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    branches:
      - main

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: true

jobs:
  release:
    name: Changesets Release
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write

    outputs:
      published: ${{ steps.changesets.outputs.published }}
      publishedPackages: ${{ steps.changesets.outputs.publishedPackages }}

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # changesets needs full history for diff

      - uses: pnpm/action-setup@v3
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Create Release PR or Publish
        id: changesets
        uses: changesets/action@v1
        with:
          publish: pnpm changeset publish
          version: pnpm changeset version
          commit: "chore: version packages"
          title: "chore: version packages"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NPM_TOKEN:    ${{ secrets.NPM_TOKEN }}   # only needed if publishing to npm

  deploy-workers:
    name: Deploy Changed Workers
    needs: release
    if: needs.release.outputs.published == 'true'
    runs-on: ubuntu-latest

    strategy:
      matrix:
        # changesets/action emits a JSON array like:
        # [{"name":"@acme/api-worker","version":"1.2.0"},{...}]
        package: ${{ fromJson(needs.release.outputs.publishedPackages) }}

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v3
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      # Derive the filesystem path from the package name (@acme/api-worker -> packages/api-worker)
      - name: Resolve package directory
        id: pkg
        run: |
          PKG_NAME="${{ matrix.package.name }}"
          # Strip npm scope: @acme/api-worker -> api-worker
          DIR="packages/${PKG_NAME##*/}"
          echo "dir=$DIR" >> "$GITHUB_OUTPUT"

      - name: Deploy Worker — ${{ matrix.package.name }}@${{ matrix.package.version }}
        working-directory: ${{ steps.pkg.outputs.dir }}
        run: pnpm exec wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## Contributor Workflow

```bash
# After making changes in packages/api-worker:
pnpm changeset add
# ? Which packages would you like to include? › packages/api-worker
# ? What kind of change is this for @acme/api-worker? › patch
# ? Please enter a summary for this change › fix: return 400 on missing user-id header
# Changeset added! - .changeset/bright-lions-fall.md

# Commit the changeset alongside your code changes
git add .changeset/bright-lions-fall.md
git commit -m "fix: return 400 on missing user-id header"
git push origin fix/missing-user-id-header
# Open PR as normal
```

The generated changeset file looks like:

```markdown
---
"@acme/api-worker": patch
---

fix: return 400 on missing user-id header
```

---

## Version Bumping Locally (Optional Pre-flight)

```bash
# Preview what versions would be bumped without writing anything
pnpm changeset status

# Actually bump versions and write changelogs (done by CI, but useful locally)
pnpm changeset version
git diff packages/api-worker/package.json
# -  "version": "1.1.3",
# +  "version": "1.1.4",

# Undo if you were just previewing
git checkout -- .
```

---

## Package.json Requirements

Each Worker package must have a `name` field that matches the changeset scope and a `private: true` flag (unless you are genuinely publishing to npm):

```jsonc
// packages/api-worker/package.json
{
  "name": "@acme/api-worker",
  "version": "1.1.3",
  "private": true,
  "scripts": {
    "deploy": "wrangler deploy",
    "types": "wrangler types"
  }
}
```

```jsonc
// packages/shared/package.json  — a shared library consumed by Workers
{
  "name": "@acme/shared",
  "version": "2.0.1",
  "private": true
}
```

With `"updateInternalDependencies": "patch"` in `config.json`, bumping `@acme/shared` automatically issues a patch bump to every Worker that depends on it.

---

## Anti-patterns

- **Skipping `changeset add` before merging** — Changesets Action creates a "Version Packages" PR; if that PR is merged with no changesets, nothing is versioned and no deploy runs. Enforce changeset presence with the [changeset-bot](https://github.com/apps/changeset-bot) GitHub App.
- **Deploying inside the `release` job** — the `release` job runs on every push to `main`, including the "Version Packages" merge commit. Separating deploy into a `deploy-workers` job gated on `published == 'true'` prevents double-deploys.
- **Using `access: public` for Workers** — Workers are not npm packages. Set `"access": "restricted"` and skip `NPM_TOKEN` unless you are also publishing a shared library.
- **Hardcoding the package directory path** — derive it from `matrix.package.name` (as shown above) so the workflow stays correct when packages are renamed.

---

## Gotchas

- `changesets/action` opens a PR titled "chore: version packages" against `main`. If branch protection rules require PR reviews, that PR also requires a review before the deploy runs. Add the `changeset-bot` as an approved reviewer, or use a `GITHUB_TOKEN` with bypass rights.
- `fetch-depth: 0` is required. Changesets diffs tags to determine what has changed; a shallow clone causes `changeset publish` to fail silently or tag incorrectly.
- If you rename a package's `name` field in `package.json`, any open changesets referencing the old name become orphaned. Re-run `changeset add` with the new name.
- The `publishedPackages` output is an empty JSON array `[]` (not the string `'false'`) when nothing is published, so always gate on `published == 'true'`, not on `publishedPackages != '[]'`.

---

## Verification

```bash
# Check that changesets are present before merging
pnpm changeset status
# Found 1 changeset. Will release: @acme/api-worker@patch

# After the release PR merges, confirm tags were created
git fetch --tags
git tag --list | grep api-worker
# @acme/api-worker@1.1.4

# Confirm the Worker was deployed
npx wrangler deployments list --name api-worker
# Most recent: 2026-08-24 ...  Version: 1.1.4
```

---

## Related

- `github-actions-path-filter-selective-deploy-workers.md`
- `git-worktree-hotfix-production-without-stash.md`
- [Changesets documentation](https://github.com/changesets/changesets)
- [changesets/action GitHub Action](https://github.com/changesets/action)

## Sources

- Changesets official documentation (2024)
- Cloudflare Workers Wrangler CLI documentation (2026)
- example.com internal runbook: "Monorepo release process" (2025)
