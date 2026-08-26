# Automated GitHub Release and Changelog for Workers Projects

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Workers project has no consistent release process: versions are bumped manually, changelogs are forgotten, and there's no clear signal to trigger a production deploy after a release. You need an automated pipeline where conventional commits on `main` drive version bumps, changelog generation, GitHub Release creation, git tagging, and a `wrangler deploy` trigger — all without manual steps.

---

## Context
`release-please` is a Google-maintained GitHub Action that reads conventional commit messages (`feat:`, `fix:`, `chore:`, `BREAKING CHANGE:`) and maintains a release PR that accumulates pending changes. When the release PR is merged, `release-please` creates a GitHub Release and git tag automatically. For monorepos, `release-please-manifest.json` maps each package directory to its own version, enabling independent versioning of Workers packages. The release event then triggers a separate deploy workflow that runs `wrangler deploy` for the newly tagged package, completing the full release chain.

---

## Setup / Config

```yaml
# release-please-config.json — single-package Worker
{
  "release-type": "node",
  "packages": {
    ".": {
      "release-type": "node",
      "changelog-path": "CHANGELOG.md",
      "bump-minor-pre-major": true,
      "bump-patch-for-minor-pre-major": true,
      "draft": false,
      "prerelease": false
    }
  },
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json"
}
```

```json
// .release-please-manifest.json — tracks current versions
{
  ".": "1.4.2"
}
```

```json
// release-please-config.json — monorepo variant
{
  "release-type": "node",
  "packages": {
    "packages/api-worker": {
      "release-type": "node",
      "changelog-path": "CHANGELOG.md",
      "component": "api-worker"
    },
    "packages/auth-worker": {
      "release-type": "node",
      "changelog-path": "CHANGELOG.md",
      "component": "auth-worker"
    },
    "packages/storefront-worker": {
      "release-type": "node",
      "changelog-path": "CHANGELOG.md",
      "component": "storefront-worker"
    }
  },
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json"
}
```

```json
// .release-please-manifest.json — monorepo variant
{
  "packages/api-worker": "2.1.0",
  "packages/auth-worker": "1.0.5",
  "packages/storefront-worker": "3.2.1"
}
```

---

## Implementation

```yaml
# .github/workflows/release-please.yml
name: Release Please

on:
  push:
    branches: [main]

permissions:
  contents: write
  pull-requests: write

jobs:
  release-please:
    runs-on: ubuntu-latest
    outputs:
      release_created: ${{ steps.release.outputs.release_created }}
      tag_name: ${{ steps.release.outputs.tag_name }}
      major: ${{ steps.release.outputs.major }}
      minor: ${{ steps.release.outputs.minor }}
    steps:
      - uses: googleapis/release-please-action@v4
        id: release
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          config-file: release-please-config.json
          manifest-file: .release-please-manifest.json
```

```yaml
# .github/workflows/deploy-on-release.yml
name: Deploy on Release

on:
  release:
    types: [published]

env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.release.tag_name }}

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      - name: Deploy Worker at release tag
        run: npx wrangler deploy --env production

      - name: Notify release deployed
        run: |
          echo "Deployed version ${{ github.event.release.tag_name }} to production"
          echo "Release URL: ${{ github.event.release.html_url }}"
```

---

## Integration / Testing

```bash
# Conventional commit examples that drive release-please versioning:
# patch bump (fix):
git commit -m "fix: handle null response from D1 query"

# minor bump (feat):
git commit -m "feat: add rate limiting middleware to api-worker"

# major bump (breaking change):
git commit -m "feat!: remove v1 API endpoints"
# or with footer:
git commit -m "refactor: restructure auth flow

BREAKING CHANGE: JWT shape has changed, clients must update"

# After pushing to main, release-please opens or updates a Release PR
# View open release PRs:
gh pr list --label autorelease:pending

# Merge the release PR to trigger GitHub Release creation:
gh pr merge <release-pr-number> --squash

# After merge, verify GitHub Release was created:
gh release list --limit 5

# Verify the deploy workflow triggered:
gh run list --workflow deploy-on-release.yml --limit 3
```

---

## Anti-patterns
- **Manually editing `CHANGELOG.md`** — `release-please` owns the changelog file; manual edits cause merge conflicts on the next release PR and may be overwritten.
- **Using `v` prefix inconsistently in tags** — `release-please` creates tags like `v1.2.3` by default; mixing with unversioned tags or `1.2.3` breaks the manifest's version tracking.
- **Triggering deploy on push to main instead of release** — Deploying every commit to main skips the versioning step and means production always runs unreleased code without a changelog.
- **Not pinning `release-please-action` to a major version** — Use `@v4` (major) not `@main` to avoid unexpected breaking changes from upstream commits.
- **Single manifest for a monorepo without component names** — Without `"component": "package-name"` in each package config, `release-please` generates ambiguous tag names that collide in monorepos.

---

## Gotchas
- `release-please` requires `contents: write` and `pull-requests: write` permissions; with the default `GITHUB_TOKEN` this works unless your org requires a PAT for protected branches.
- The first time `release-please` runs, it creates a bootstrap commit to set up the manifest; this is expected and can be merged directly.
- `release-please` batches multiple conventional commits into a single release PR update; it won't create a new PR for every commit, it will update the existing open one.
- If you squash-merge feature branches into main, only the squash commit message is read; ensure the squash commit message follows conventional commit format.
- The `release` event with type `published` fires for both manually created and `release-please`-automated releases; add a tag name filter if you want to deploy only `release-please` tags.

---

## Verification

```bash
# Confirm release-please manifest is up to date after a release
cat .release-please-manifest.json
# Version should match the latest tag

# Confirm GitHub Release exists with correct tag
gh release view v1.5.0

# Confirm CHANGELOG.md was updated
git log --oneline CHANGELOG.md | head -5

# Confirm Worker deployed at the released version
curl -s https://my-worker.my-subdomain.workers.dev/version
# Should return the version matching the release tag

# Confirm deploy workflow ran successfully
gh run list --workflow deploy-on-release.yml --status success --limit 3
```

---

## Related
- `github-required-status-checks-workers-ci.md`
- `github-actions-d1-migration-ci.md`
- `wrangler-deploy-env-production.md`

---

## Sources
- release-please GitHub Action — https://github.com/googleapis/release-please-action
- release-please Configuration Reference — https://github.com/googleapis/release-please/blob/main/docs/manifest-releaser.md
- Conventional Commits Specification — https://www.conventionalcommits.org/en/v1.0.0/
- GitHub Releases Documentation — https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository
