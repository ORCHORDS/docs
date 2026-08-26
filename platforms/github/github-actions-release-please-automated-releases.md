# GitHub Actions: release-please for Automated Changelogs and Semantic Releases

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your team follows Conventional Commits but changelog maintenance is still manual:
- Someone has to run `npm version`, edit CHANGELOG.md, tag, push, create a GitHub Release.
- Release notes drift from what actually changed.
- Hotfix branches and merged PRs get out of sync with version numbers.

`release-please` (maintained by Google) solves this by automating the entire release lifecycle as a GitHub Actions workflow: it reads Conventional Commits, bumps `version` fields in manifests, writes `CHANGELOG.md`, opens a "Release PR", and creates the GitHub Release when that PR merges.

---

## Context

`release-please` works via a two-phase model:

1. **Release PR phase.** On every push to the default branch `release-please` evaluates unreleased commits, computes the next semver (patch / minor / major), updates manifest files, and opens (or updates) a long-lived PR titled `chore(main): release X.Y.Z`. The PR accumulates changes until a human merges it.

2. **Release creation phase.** When the Release PR merges, `release-please` reads the merge commit, creates a git tag `vX.Y.Z`, and publishes a GitHub Release with the accumulated changelog.

No commits or tags are created by the workflow itself — everything goes through GitHub's standard merge path, preserving full audit history.

### Supported versioning strategies

| Strategy | Description |
|---|---|
| `simple` | Single manifest, single package (default) |
| `node` | Bumps `package.json` version |
| `python` | Bumps `setup.cfg` / `pyproject.toml` |
| `go` | Updates `go.mod` major suffix |
| `terraform-module` | Reads module source semver |
| `manifest` | Multi-package monorepo (covered below) |

---

## Basic Single-Package Setup

### 1. Workflow file

```yaml
# .github/workflows/release-please.yml
name: release-please

on:
  push:
    branches:
      - main

permissions:
  contents: write
  pull-requests: write

jobs:
  release-please:
    runs-on: ubuntu-latest
    steps:
      - uses: googleapis/release-please-action@v4
        id: release
        with:
          release-type: node   # or python, simple, go, etc.
```

`contents: write` is required to push the changelog update commit and create the Release.
`pull-requests: write` is required to open and update the Release PR.

### 2. Chaining a publish step

The action outputs `release_created` (boolean) and `tag_name` so you can gate a publish job:

```yaml
jobs:
  release-please:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    outputs:
      release_created: ${{ steps.rp.outputs.release_created }}
      tag_name: ${{ steps.rp.outputs.tag_name }}
    steps:
      - uses: googleapis/release-please-action@v4
        id: rp
        with:
          release-type: node

  publish-npm:
    needs: release-please
    if: needs.release-please.outputs.release_created == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ needs.release-please.outputs.tag_name }}

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          registry-url: https://registry.npmjs.org

      - run: npm ci
      - run: npm publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

---

## Monorepo Setup with `manifest` Strategy

For repos containing multiple independently-versioned packages:

### release-please-config.json

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "release-type": "node",
  "packages": {
    "packages/api": {
      "release-type": "node",
      "component": "api"
    },
    "packages/web": {
      "release-type": "node",
      "component": "web"
    },
    "packages/cli": {
      "release-type": "node",
      "component": "cli"
    }
  },
  "separate-pull-requests": true
}
```

### .release-please-manifest.json

```json
{
  "packages/api": "1.4.2",
  "packages/web": "0.9.0",
  "packages/cli": "2.1.0"
}
```

### Workflow for manifest strategy

```yaml
jobs:
  release-please:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
    outputs:
      paths_released: ${{ steps.rp.outputs.paths_released }}
    steps:
      - uses: googleapis/release-please-action@v4
        id: rp
        with:
          config-file: release-please-config.json
          manifest-file: .release-please-manifest.json
```

When `separate-pull-requests: true` is set each package gets its own Release PR, so releases are independent. Remove it to batch all packages into a single PR when you prefer coordinated releases.

---

## Controlling Conventional Commit Bump Behaviour

`release-please` follows the Conventional Commits spec by default:

| Commit prefix | Semver bump |
|---|---|
| `fix:` | patch |
| `feat:` | minor |
| `feat!:` or `BREAKING CHANGE:` footer | major |
| `chore:`, `docs:`, `test:` | none (included in changelog under non-bump section) |

Override the bump table via `release-please-config.json`:

```json
{
  "release-type": "simple",
  "bump-minor-pre-major": true,
  "bump-patch-for-minor-pre-major": true,
  "extra-files": [
    {
      "type": "json",
      "path": "src/version.json",
      "jsonpath": "$.version"
    }
  ],
  "changelog-sections": [
    {"type": "feat",     "section": "Features"},
    {"type": "fix",      "section": "Bug Fixes"},
    {"type": "perf",     "section": "Performance Improvements"},
    {"type": "revert",   "section": "Reverts"},
    {"type": "docs",     "section": "Documentation", "hidden": false},
    {"type": "chore",    "section": "Miscellaneous", "hidden": true}
  ]
}
```

`extra-files` lets release-please bump version strings in arbitrary files beyond the primary manifest (useful for `.env.example`, `Cargo.toml`, `Chart.yaml`, etc.).

---

## Forcing a Release or Skipping Commits

### Force a release when no releasable commits exist

Add a commit with a `fix: ` prefix to trigger a patch bump, or label the Release PR with `autorelease: pending` manually to trigger the creation step.

### Skip a commit from the changelog

Append `Release-As: skip` to a commit body, or use the `!` breaking-change flag only when needed.

### Force a specific version

```
chore: release 3.0.0

Release-As: 3.0.0
```

The `Release-As:` footer in any commit body instructs release-please to target that exact version regardless of what the commit type would compute.

---

## Anti-patterns

- **Committing directly to main without Conventional Commit prefixes.** `release-please` ignores non-conforming commits. CI passes, the Release PR accumulates nothing, and the team wonders why no release appeared. Enforce commit conventions with `commitlint` in a PR check.

- **Running release-please on multiple branches simultaneously.** release-please tracks released commits per branch. Running it on `main` and `release/v2` at the same time causes duplicate Release PRs and conflicting `.release-please-manifest.json` updates.

- **Merging the Release PR with squash.** The merge commit body must contain the changelog content. Squash strips it. Configure branch protection to require **merge commits** for the Release PR's target branch, or use the `squash-merge-changelog-entry` option.

- **Missing `pull-requests: write` permission.** The job silently fails to open the PR. Always include both `contents: write` and `pull-requests: write`.

- **Manually editing `CHANGELOG.md`.** release-please will overwrite manual edits the next time it updates the Release PR. Keep all changelog content in commit messages and PR bodies.

---

## Gotchas

- **First run needs a baseline tag.** If the repo has no existing tags release-please creates a Release PR for `v1.0.0` (or `v0.1.0` with `bump-minor-pre-major: true`). Merge it to establish the baseline; subsequent releases build from there.

- **Release PR not appearing.** This usually means there are no eligible commits (all prefixes are `chore:`, `docs:` etc.) or the `GITHUB_TOKEN` lacks `pull-requests: write`. Check the Actions run logs for `No changes to release`.

- **The `.release-please-manifest.json` must be committed.** For the manifest strategy, both the config and the manifest files must exist in the repo. release-please will fail with a `404` if the manifest file is absent.

- **Bot PRs bypass required-reviewer rules by default.** If branch protection requires at least one approval, the Release PR (opened by `github-actions[bot]`) will be blocked. Either add `github-actions[bot]` as an allowed merge-without-review actor in your ruleset, or use a GitHub App token with bypass permission.

- **Tag protection rules.** If you protect tags matching `v*`, release-please's tag creation step needs the `github-actions[bot]` actor explicitly allowed under the tag protection rule.

---

## Verification

```bash
# Confirm the Release PR exists and targets the right version
gh pr list --label "autorelease: pending" --state open

# After merge: confirm the tag and Release were created
gh release list --limit 5

# Inspect generated changelog section
gh release view v$(cat .release-please-manifest.json | jq -r '."."') \
  --json body --jq '.body' | head -40
```

---

## Related

- `github-actions-semver-bump.md` — manual semver bumping approaches
- `github-actions-create-release.md` — raw `gh release create` patterns
- `github-immutable-release-publication-and-verification.md` — signing and attesting releases
- `github-actions-workflow-dispatch.md` — triggering publish steps manually
- `github-actions-reusable-workflows.md` — extracting the publish step into a shared workflow

---

## Sources

- release-please GitHub repository — https://github.com/googleapis/release-please
- googleapis/release-please-action — https://github.com/googleapis/release-please-action
- Conventional Commits specification — https://www.conventionalcommits.org/
- release-please configuration reference — https://github.com/googleapis/release-please/blob/main/docs/manifest-releaser.md
