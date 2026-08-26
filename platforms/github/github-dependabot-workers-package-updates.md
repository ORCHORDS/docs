# Automated Dependency Updates for Workers Projects with Dependabot

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A monorepo with multiple Workers under `workers/` accumulates stale npm dependencies silently. Security patches for `wrangler`, `@cloudflare/workers-types`, and shared utilities land weeks after release because no automated process tracks them. Manually auditing five separate `package.json` files before each deploy is error-prone and time-consuming.

---

## Context

GitHub Dependabot can monitor multiple directories for npm updates, open grouped pull requests, and trigger auto-merge workflows when CI passes. Grouping all `@cloudflare/*` and `wrangler` packages into a single PR reduces noise while still keeping each bump independently reviewable. Ignoring `wrangler` major version bumps prevents breaking changes from auto-merging, since Wrangler majors frequently require `wrangler.toml` schema changes. Patch-level updates that pass CI are safe to auto-merge via the `gh` CLI or the `peter-evans/enable-pull-request-automerge` action.

---

## Section 1 — Dependabot configuration

```yaml
# .github/dependabot.yml
version: 2
updates:
  # Root package (shared devDependencies, scripts)
  - package-ecosystem: npm
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
      timezone: UTC
    open-pull-requests-limit: 5
    groups:
      cloudflare-toolchain:
        patterns:
          - "wrangler"
          - "@cloudflare/*"
        update-types:
          - minor
          - patch
    ignore:
      # Never auto-bump wrangler major versions; they often require
      # wrangler.toml schema changes and manual migration steps.
      - dependency-name: "wrangler"
        update-types: ["version-update:semver-major"]
    labels:
      - dependencies
      - automated
    commit-message:
      prefix: "chore"
      include: scope

  # workers/api
  - package-ecosystem: npm
    directory: /workers/api
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
      timezone: UTC
    open-pull-requests-limit: 3
    groups:
      cloudflare-toolchain:
        patterns:
          - "wrangler"
          - "@cloudflare/*"
        update-types:
          - minor
          - patch
    ignore:
      - dependency-name: "wrangler"
        update-types: ["version-update:semver-major"]
    labels:
      - dependencies
      - automated
      - worker:api

  # workers/auth
  - package-ecosystem: npm
    directory: /workers/auth
    schedule:
      interval: weekly
      day: monday
      time: "06:10"
      timezone: UTC
    open-pull-requests-limit: 3
    groups:
      cloudflare-toolchain:
        patterns:
          - "wrangler"
          - "@cloudflare/*"
        update-types:
          - minor
          - patch
    ignore:
      - dependency-name: "wrangler"
        update-types: ["version-update:semver-major"]
    labels:
      - dependencies
      - automated
      - worker:auth

  # workers/webhooks
  - package-ecosystem: npm
    directory: /workers/webhooks
    schedule:
      interval: weekly
      day: monday
      time: "06:20"
      timezone: UTC
    open-pull-requests-limit: 3
    groups:
      cloudflare-toolchain:
        patterns:
          - "wrangler"
          - "@cloudflare/*"
        update-types:
          - minor
          - patch
    ignore:
      - dependency-name: "wrangler"
        update-types: ["version-update:semver-major"]
    labels:
      - dependencies
      - automated
      - worker:webhooks

  # GitHub Actions themselves
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:30"
      timezone: UTC
    open-pull-requests-limit: 5
    groups:
      actions:
        patterns: ["*"]
    labels:
      - dependencies
      - github-actions
      - automated
```

---

## Section 2 — Auto-merge workflow for patch Dependabot PRs

```yaml
# .github/workflows/dependabot-auto-merge.yml
name: Dependabot Auto-merge

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    # Only run for Dependabot PRs
    if: github.actor == 'dependabot[bot]'
    steps:
      - name: Fetch Dependabot metadata
        id: metadata
        uses: dependabot/fetch-metadata@v2
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Approve patch and minor updates
        if: |
          steps.metadata.outputs.update-type == 'version-update:semver-patch' ||
          (steps.metadata.outputs.update-type == 'version-update:semver-minor' &&
           contains(steps.metadata.outputs.dependency-names, '@cloudflare/'))
        run: gh pr review --approve "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Enable auto-merge for safe updates
        if: |
          steps.metadata.outputs.update-type == 'version-update:semver-patch'
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Section 3 — CI workflow that gates auto-merge

```yaml
# .github/workflows/ci.yml  (excerpt — the required status check)
name: CI

on:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        worker: [api, auth, webhooks]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - name: Install root deps
        run: npm ci
      - name: Install worker deps
        run: npm ci
        working-directory: workers/${{ matrix.worker }}
      - name: Type-check
        run: npx tsc --noEmit
        working-directory: workers/${{ matrix.worker }}
      - name: Test
        run: npm test
        working-directory: workers/${{ matrix.worker }}
      - name: Dry-run wrangler deploy
        run: npx wrangler deploy --dry-run --outdir /tmp/dist
        working-directory: workers/${{ matrix.worker }}
        env:
          CLOUDFLARE_API_TOKEN: placeholder
          CLOUDFLARE_ACCOUNT_ID: placeholder
```

---

## Anti-patterns

- **Single `directory: /` for all Workers** — Dependabot only reads one `package.json` per directory entry; if your Workers have separate `package.json` files you must add a separate `updates` block per directory or their deps will be silently ignored.
- **Auto-merging `wrangler` major bumps** — Wrangler 3→4 introduced breaking changes to `wrangler.toml` syntax and deprecated several CLI flags. Always review major Wrangler bumps manually.
- **No required status checks on the branch** — Auto-merge merges immediately if no required checks are configured. Set at least the `test` job as a required check in branch protection rules before enabling auto-merge.
- **`open-pull-requests-limit: 10` without groups** — Without grouping, Dependabot opens one PR per package, flooding the queue and making reviewers ignore them all.

---

## Gotchas

- Dependabot PRs from `dependabot[bot]` do not have access to repository secrets by default. If your CI workflow requires secrets (e.g. `CLOUDFLARE_API_TOKEN`), use the `pull_request_target` event carefully or rely on `--dry-run` deploys that accept placeholder values.
- The `groups` key requires Dependabot version 2 schema. Confirm `version: 2` is set at the top of `.github/dependabot.yml`.
- Staggering schedule times per directory (`:06:00`, `06:10`, `06:20`) prevents all Dependabot jobs from hitting the npm registry simultaneously, avoiding rate-limit errors.
- `dependabot/fetch-metadata` must be pinned to a major version tag (`@v2`); floating `@latest` can break auto-merge workflows when the action introduces breaking changes.

---

## Verification

```bash
# Validate the dependabot.yml schema
npx --yes @dependabot/cli validate .github/dependabot.yml

# List open Dependabot PRs
gh pr list --author 'dependabot[bot]' --label dependencies

# Check auto-merge status on the latest Dependabot PR
gh pr view $(gh pr list --author 'dependabot[bot]' --limit 1 --json number -q '.[0].number') \
  --json autoMergeRequest | jq '.autoMergeRequest'

# Trigger Dependabot to re-check now (requires admin token)
gh api \
  --method POST \
  /repos/{owner}/{repo}/dependabot/alerts/auto_dismissed_alerts \
  || echo "Use the GitHub UI: Insights → Dependency graph → Dependabot → Check for updates"
```

---

## Related

- `github-actions-wrangler-matrix-deploy.md`
- `github-pr-preview-cloudflare-pages-comment.md`

---

## Sources

- GitHub Dependabot configuration options — https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file
- Dependabot grouped updates — https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file#groups
- dependabot/fetch-metadata action — https://github.com/dependabot/fetch-metadata
- Wrangler changelog — https://github.com/cloudflare/workers-sdk/blob/main/packages/wrangler/CHANGELOG.md
