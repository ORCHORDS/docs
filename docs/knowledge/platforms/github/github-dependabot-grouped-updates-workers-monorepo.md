# Dependabot Grouped Version Updates for Workers Monorepos

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

In a Cloudflare Workers monorepo each package-level `package.json` declares overlapping
dependencies (`hono`, `zod`, `@cloudflare/workers-types`, `wrangler`). Without grouping,
Dependabot opens **one PR per package per dependency bump** — a 10-package monorepo receiving
5 patch bumps generates 50 PRs in a week. Review fatigue sets in and PRs pile up un-merged.

Dependabot's `groups:` key (GA since late 2023) collapses related dependency bumps into a
single PR per ecosystem per group, slashing noise by an order of magnitude.

---

## Context

The `groups:` key lives under each `updates:` block in `.github/dependabot.yml`. Each group
has a `patterns:` list of glob-style dependency name filters and an optional `update-types:`
list (`patch`, `minor`, `major`). Dependabot evaluates groups in order; a dependency matches
the **first** group whose pattern it satisfies. Unmatched dependencies still get individual PRs.

Groups interact with:
- **`ignore:` rules** — ignored deps are excluded before grouping
- **Security updates** — security-triggered PRs are never grouped; they always get individual PRs
  regardless of group membership (this is intentional — security PRs need targeted review)
- **`versioning-strategy:`** — still applied per-dependency within a group

---

## Basic `.github/dependabot.yml` for a Workers Monorepo

```yaml
# .github/dependabot.yml
version: 2

updates:
  # ── npm/pnpm dependencies ──────────────────────────────────────────────────
  - package-ecosystem: "npm"
    directory: "/"            # workspace root (pnpm-workspace.yaml lives here)
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Europe/London"
    open-pull-requests-limit: 10

    # ── Groups ──────────────────────────────────────────────────────────────
    groups:
      # All Cloudflare-first-party packages in one PR
      cloudflare-runtime:
        patterns:
          - "wrangler"
          - "@cloudflare/*"
          - "miniflare"
        update-types:
          - "minor"
          - "patch"

      # Hono framework and its official middleware
      hono-ecosystem:
        patterns:
          - "hono"
          - "@hono/*"
        update-types:
          - "minor"
          - "patch"

      # Schema / validation libraries
      validation:
        patterns:
          - "zod"
          - "valibot"
          - "@sinclair/typebox"
        update-types:
          - "minor"
          - "patch"

      # All TypeScript toolchain packages
      typescript-toolchain:
        patterns:
          - "typescript"
          - "tsup"
          - "tsx"
          - "@types/*"
          - "ts-node"
        update-types:
          - "minor"
          - "patch"

      # Test infrastructure
      test-tooling:
        patterns:
          - "vitest"
          - "@vitest/*"
          - "jest"
          - "@jest/*"
        update-types:
          - "minor"
          - "patch"

      # All ESLint packages
      linting:
        patterns:
          - "eslint"
          - "@eslint/*"
          - "@typescript-eslint/*"
          - "eslint-*"
        update-types:
          - "minor"
          - "patch"

    # Keep major bumps as individual PRs so they get explicit sign-off
    ignore:
      - dependency-name: "*"
        update-types:
          - "version-update:semver-major"   # still creates individual PRs, not ignored

  # ── GitHub Actions ─────────────────────────────────────────────────────────
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
      timezone: "Europe/London"
    open-pull-requests-limit: 5

    groups:
      cloudflare-actions:
        patterns:
          - "cloudflare/*"
        update-types:
          - "minor"
          - "patch"

      github-official-actions:
        patterns:
          - "actions/*"
        update-types:
          - "minor"
          - "patch"
```

> **`directory: "/"`** works for pnpm workspaces — Dependabot reads `pnpm-workspace.yaml` and
> processes all workspace packages automatically. You do **not** need one `updates:` block per
> workspace package.

---

## PR Output

With the above config, a week with 12 updated packages might produce:

| Group PR title | Deps bundled |
|----------------|-------------|
| `chore(deps): bump cloudflare-runtime group` | wrangler, @cloudflare/workers-types |
| `chore(deps): bump hono-ecosystem group` | hono, @hono/zod-validator |
| `chore(deps): bump typescript-toolchain group` | typescript, tsup, @types/node |
| `chore(deps): bump test-tooling group` | vitest, @vitest/coverage-v8 |
| `chore(deps): bump github-official-actions group` | actions/checkout, actions/setup-node |

Individual PRs are still created for anything without a matching group (e.g., a one-off `luxon`
upgrade) and for **all security updates**.

---

## Auto-merge Strategy for Grouped PRs

Pair grouping with conditional auto-merge so low-risk patch/minor PRs merge without human
intervention:

```yaml
# .github/workflows/dependabot-auto-merge.yml
name: Dependabot auto-merge
on: pull_request

permissions:
  contents: write
  pull-requests: write

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    if: github.actor == 'dependabot[bot]'

    steps:
      - name: Fetch Dependabot metadata
        id: meta
        uses: dependabot/fetch-metadata@v2
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Auto-merge patch/minor group PRs after CI passes
        # Only auto-merge grouped PRs; leave individual major PRs for human review
        if: |
          steps.meta.outputs.update-type != 'version-update:semver-major' &&
          steps.meta.outputs.dependency-group != ''
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

The `dependency-group` output from `dependabot/fetch-metadata` is non-empty only when the PR
was created by a group, making it a reliable discriminator.

---

## Handling Mixed update-types Within a Group

If you want a group to cover **both** minor and major, omit `update-types:` entirely — the group
then matches all update types:

```yaml
groups:
  cloudflare-runtime:
    patterns:
      - "wrangler"
      - "@cloudflare/*"
    # no update-types key → matches patch, minor, AND major
```

This is useful when you trust Cloudflare's semver discipline enough to auto-merge major wrangler
bumps. Most teams prefer to keep major bumps ungrouped, so the auto-merge workflow can gate them.

---

## Excluding a Dependency from All Groups

Use `exclude-patterns:` inside a group definition (introduced mid-2024):

```yaml
groups:
  cloudflare-runtime:
    patterns:
      - "@cloudflare/*"
    exclude-patterns:
      - "@cloudflare/vitest-pool-workers"   # kept separate for careful review
```

The excluded dep falls through to the next matching group or becomes an individual PR.

---

## Scoping Groups to a Subdirectory (Non-workspace repos)

If your monorepo does **not** use npm/pnpm workspaces, create one `updates:` block per
Worker app and repeat the groups:

```yaml
updates:
  - package-ecosystem: "npm"
    directory: "/workers/api"
    schedule: { interval: "weekly" }
    groups:
      cloudflare-runtime:
        patterns: ["wrangler", "@cloudflare/*"]

  - package-ecosystem: "npm"
    directory: "/workers/auth"
    schedule: { interval: "weekly" }
    groups:
      cloudflare-runtime:
        patterns: ["wrangler", "@cloudflare/*"]
```

Group names are local to each `updates:` block — duplicate names across blocks are fine.

---

## Anti-patterns

- **One giant catch-all group** — a group matching `"*"` creates one huge PR with dozens of
  packages, making it impossible to bisect a breakage. Prefer topically coherent groups.

- **Grouping security updates** — Dependabot silently ignores `groups:` for security-triggered
  PRs. Do not write logic that assumes security PRs are grouped; they never are.

- **`open-pull-requests-limit: 0`** — setting this to zero disables Dependabot entirely,
  including security updates. Use a positive value (≥ 5) even if you prefer grouped PRs.

- **Missing `ignore:` for lock-file-only changes** — if you want to suppress PRs that only
  update `pnpm-lock.yaml` without changing manifest ranges, add:
  ```yaml
  ignore:
    - dependency-name: "*"
      update-types: ["version-update:semver-patch"]
  ```
  and rely on `pnpm install --frozen-lockfile` in CI instead.

---

## Gotchas

- **Groups reset on config change** — editing `dependabot.yml` (even whitespace) causes
  Dependabot to re-evaluate all pending updates and may re-open or close grouped PRs.

- **Workspace root must be resolvable** — pnpm workspaces declared in `pnpm-workspace.yaml`
  at `/` are auto-discovered. If your workspace root is a subdirectory (`packages/`), set
  `directory: "/packages"`.

- **`dependency-group` metadata output requires `fetch-metadata` v2+** — earlier versions of
  the action do not expose the group name. Pin to `dependabot/fetch-metadata@v2`.

- **Rebase conflicts in grouped PRs** — a grouped PR touching `pnpm-lock.yaml` across many
  packages will conflict with other grouped PRs on the same branch. Configure branch protection
  to require PRs to be up-to-date before merging, and enable GitHub's auto-update on merge queue.

- **`schedule.day` is UTC** — the day boundary is midnight UTC. A `"monday"` schedule with
  `timezone: "America/Los_Angeles"` still opens PRs when it becomes Monday in UTC (UTC midnight),
  not Monday morning in LA time.

---

## Verification

```bash
# After updating dependabot.yml, trigger a manual check
gh api repos/{owner}/{repo}/dependabot/updates --method POST || true

# List open Dependabot PRs grouped by the dependency-group label
gh pr list --author app/dependabot --json title,labels \
  --jq '.[] | select(.labels[].name | startswith("dependencies")) | .title'

# Confirm a PR was created by a group (metadata action output)
# In Actions run logs, look for:
# dependency-group: cloudflare-runtime
```

---

## Related

- `dependabot-config.md` — base Dependabot config reference
- `dependabot-auto-merge-workers-deps.md` — auto-merge workflows
- `dependabot-multi-ecosystem-group-review-boundary.md` — cross-ecosystem group review
- `github-actions-merge-group-integration-testing.md` — merge queue with grouped PRs

---

## Sources

- https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file#groups
- https://github.blog/changelog/2023-06-30-grouped-version-updates-for-dependabot-public-beta/
- https://github.com/dependabot/fetch-metadata
- https://docs.github.com/en/code-security/dependabot/working-with-dependabot/automating-dependabot-with-github-actions
