# GitHub Actions Release Drafter Changelog Automation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

After every merge to `main`, you want a draft GitHub Release to appear
automatically with a categorised changelog built from PR titles and labels — so
that cutting a release is just bumping the version and clicking "Publish".
`release-please` (already in the KB) is great when you own the version bump
lifecycle end-to-end; **release-drafter** is the right tool when humans decide
the version and just want the notes pre-filled for a Workers monorepo where
dozens of PRs land between each release.

---

## Context

[Release Drafter](https://github.com/release-drafter/release-drafter) reads a
config file, inspects merged PRs since the last published release, and
upserts a single draft release. It maps PR labels to changelog categories,
computes the next semver, and renders a Markdown body. No commits are created;
no tags are pushed; the human publishes when ready.

For a example project Cloudflare Workers monorepo the labels align to package areas
(`worker:api-gateway`, `worker:auth`, `infra`, `deps`, `breaking`) and the
changelog surfaces per-area impact clearly.

---

## Config File

```yaml
# .github/release-drafter.yml
name-template: "v$RESOLVED_VERSION"
tag-template: "v$RESOLVED_VERSION"
change-title-escapes: '\<*_&'   # escape markdown in PR titles

# ── Version resolution ────────────────────────────────────────────────────────
version-resolver:
  major:
    labels:
      - "breaking"
      - "type: breaking change"
  minor:
    labels:
      - "feature"
      - "enhancement"
  patch:
    labels:
      - "fix"
      - "bugfix"
      - "deps"
      - "chore"
  default: patch

# ── Changelog categories ──────────────────────────────────────────────────────
categories:
  - title: "⚠️ Breaking Changes"
    labels:
      - "breaking"
      - "type: breaking change"
  - title: "🚀 New Features"
    labels:
      - "feature"
      - "enhancement"
  - title: "🐛 Bug Fixes"
    labels:
      - "fix"
      - "bugfix"
  - title: "☁️ API Gateway"
    labels:
      - "worker:api-gateway"
  - title: "🔐 Auth Worker"
    labels:
      - "worker:auth"
  - title: "🏗 Infrastructure"
    labels:
      - "infra"
      - "cloudflare"
  - title: "📦 Dependencies"
    labels:
      - "deps"
      - "dependabot"
  - title: "🔧 Maintenance"
    labels:
      - "chore"
      - "refactor"
      - "docs"

# ── Exclude non-notable PRs ────────────────────────────────────────────────────
exclude-labels:
  - "skip-changelog"
  - "release"
  - "wip"

# ── PRs not matching any category go here ─────────────────────────────────────
no-changes-template: "_No user-facing changes in this release._"

# ── Release body template ─────────────────────────────────────────────────────
template: |
  ## What's Changed

  $CHANGES

  ---
  **Full Changelog**: $PREVIOUS_TAG...$RESOLVED_VERSION
  **Contributors**: $CONTRIBUTORS

autolabeler:
  - label: "deps"
    title:
      - "/^(chore|fix)\\(deps\\)/i"
      - "/^bump /i"
  - label: "infra"
    files:
      - "infrastructure/**"
      - "wrangler.*.toml"
      - ".github/workflows/deploy-*.yml"
  - label: "worker:api-gateway"
    files:
      - "workers/api-gateway/**"
  - label: "worker:auth"
    files:
      - "workers/auth/**"
```

---

## Workflow — On Push to main

```yaml
# .github/workflows/release-drafter.yml
name: Release Drafter

on:
  push:
    branches:
      - main
  # Also allow manual re-draft (e.g. after config change)
  workflow_dispatch:

permissions:
  contents: write        # create/update draft release
  pull-requests: write   # autolabeler needs PR write to apply labels

jobs:
  update-release-draft:
    name: Update Release Draft
    runs-on: ubuntu-24.04
    steps:
      - uses: release-drafter/release-drafter@v6
        id: drafter
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Echo draft URL
        run: echo "Draft release -> ${{ steps.drafter.outputs.html_url }}"
```

---

## Workflow — Autolabel on PR Open/Edit

Release Drafter's autolabeler fires as part of the `update-release-draft` job
on push, but labelling happens _after_ merge. For earlier feedback (so reviewers
see the label on the PR), run autolabeling separately on `pull_request` events:

```yaml
# .github/workflows/autolabel-pr.yml
name: Autolabel PR

on:
  pull_request:
    types: [opened, edited, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  autolabel:
    runs-on: ubuntu-24.04
    steps:
      - uses: release-drafter/release-drafter@v6
        with:
          disable-releaser: true     # only run autolabeler, skip draft update
          disable-autolabeler: false
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Pinning the Action

Pin to a SHA to prevent supply-chain surprises:

```yaml
# Get current SHA:
#   gh release view --repo release-drafter/release-drafter --json tagName,targetCommitish
- uses: release-drafter/release-drafter@3f0f87fd428f3048bd8f8b6b14a1bd25fca20c3
  # v6.1.0 — update this SHA when upgrading
```

Add to your SHA-pinning audit policy in `actions-policy-sha-pinning-and-blocklists-2026.md`.

---

## Monorepo Variant — Per-Package Drafts

If your monorepo releases Workers packages independently, maintain separate
config files and trigger the drafter per affected package:

```yaml
# .github/release-drafter-api-gateway.yml  (separate config per worker)
name-template: "api-gateway-v$RESOLVED_VERSION"
tag-template: "api-gateway-v$RESOLVED_VERSION"
filter-by-commitish: true    # only PRs that touched this path
commitish: main
include-paths:
  - workers/api-gateway/**
```

```yaml
# .github/workflows/release-drafter-api-gateway.yml
name: Release Drafter — API Gateway

on:
  push:
    branches: [main]
    paths:
      - "workers/api-gateway/**"
      - ".github/release-drafter-api-gateway.yml"

permissions:
  contents: write
  pull-requests: read

jobs:
  draft:
    runs-on: ubuntu-24.04
    steps:
      - uses: release-drafter/release-drafter@v6
        with:
          config-name: release-drafter-api-gateway.yml
          header: "## api-gateway"
          tag: "api-gateway-v$RESOLVED_VERSION"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Publishing a Release via CLI

Once the draft looks good, publish from the CLI (no UI required):

```bash
# List draft releases
gh release list --repo your-org/example project-monorepo | grep Draft

# Edit the version tag if needed, then publish
gh release edit "v1.4.0" --draft=false --latest

# Or create and publish from the draft body in one step
BODY=$(gh release view "v1.4.0" --json body --jq '.body')
gh release create "v1.4.0" \
  --title "v1.4.0" \
  --notes "$BODY" \
  --latest \
  --target main
```

---

## CI Gate on Release Publish

Trigger the production deploy when a release is published (not drafted):

```yaml
# .github/workflows/deploy-on-release.yml
on:
  release:
    types: [published]

jobs:
  deploy:
    if: "!github.event.release.prerelease"
    uses: ./.github/workflows/deploy-worker.yml
    with:
      worker_name: api-gateway
      version: ${{ github.event.release.tag_name }}
    secrets: inherit
```

---

## Anti-patterns

- **Running release-drafter on `pull_request_target`**: exposes write tokens to
  untrusted forks. Use `pull_request` for autolabeling (read token only) and
  `push` for draft updates (write token on protected branch context).
- **Granting `contents: write` on the autolabel-only workflow**: autolabeling
  only needs `pull-requests: write`; `contents: write` is only required for the
  draft creation step.
- **Using `$NEXT_PATCH_VERSION` directly in config without a resolver**: the
  resolved version respects labels; hardcoding `NEXT_PATCH_VERSION` ignores
  major/minor bump signals from PR labels.
- **Relying on release-drafter for changelogs in packages published to npm**:
  for published packages use `release-please` instead; release-drafter is a UX
  tool for human-reviewed releases, not for automated publish pipelines.

---

## Gotchas

- Release Drafter finds PRs merged since the **last published** release, not
  the last draft. If you delete a draft and no published release exists, it will
  include every PR in the repo's history.
- The `filter-by-commitish` option only works with direct merges; squash/rebase
  merges need the path in `include-paths` instead.
- The `autolabeler` `title` matchers use JavaScript regex syntax. Test regexes
  at https://regex101.com with the `javascript` flavor selected.
- `$CONTRIBUTORS` lists PR authors, not commit authors. Bot PRs (Dependabot,
  Renovate) inflate this list; use `exclude-contributors` to filter them out.
- The GitHub API used by release-drafter counts against the `GITHUB_TOKEN` rate
  limit (5,000 req/hr for the installation). High-velocity repos can hit this
  on concurrent merges.

---

## Verification

```bash
# 1. Merge a PR labelled "feature" to main
# 2. Confirm the workflow ran
gh run list --workflow=release-drafter.yml --limit 1

# 3. View the generated draft
gh release list --limit 5

# 4. View the draft body
gh release view --json body,tagName | jq '.tagName, .body'

# 5. Confirm version bump logic (minor bump for "feature" label)
# Expected: if last published was v1.3.2, draft should be v1.4.0
```

---

## Related

- `github-actions-release-please-automated-releases.md`
- `github-labels-automation.md`
- `github-actions-create-release.md`
- `github-actions-upload-release-assets.md`
- `github-immutable-release-publication-and-verification.md`

---

## Sources

- Release Drafter GitHub repo: https://github.com/release-drafter/release-drafter
- Release Drafter config schema: https://github.com/release-drafter/release-drafter#configuration-options
- GitHub Docs — Managing releases: https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository
- GitHub Docs — release event: https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#release
