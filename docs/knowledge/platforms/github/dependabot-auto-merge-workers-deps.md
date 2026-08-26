# Dependabot Auto-Merge Strategies for Cloudflare Workers Dependencies

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Workers monorepo accumulates dozens of open Dependabot PRs every week. Manually reviewing
every `patch` bump of `itty-router` or `hono` wastes engineering time. Teams want to auto-merge
safe updates while keeping a human gate on anything that could break a production Worker or its
Wrangler configuration.

## Context

Cloudflare Workers projects have a characteristic dependency graph: a small set of runtime
packages that run **inside** the Worker (`hono`, `itty-router`, `zod`, `@cloudflare/workers-types`)
and a larger set of build-time / dev tools (`wrangler`, `esbuild`, `vitest`, `typescript`).
These two groups carry different risk profiles:

- **Runtime deps** — even a patch bump can subtly change request-handling behaviour and must pass
  integration tests before merging.
- **Dev/build tools** — a patch or minor bump to `wrangler` rarely changes production behaviour
  but can break the build pipeline in unexpected ways (new Wrangler flags, changed defaults).
- **`wrangler` major versions** — should never auto-merge; they often require `wrangler.toml`
  changes, new environment variable names, or KV/D1 binding API updates.

The strategy described here uses GitHub Actions with the `gh` CLI and Dependabot's native
`auto-merge` config to implement a tiered merge policy.

## Section 1: Dependabot Configuration with Grouped Updates

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "08:00"
      timezone: "UTC"
    # Group patch bumps to reduce PR noise
    groups:
      workers-runtime-patch:
        patterns:
          - "hono"
          - "itty-router"
          - "zod"
          - "@cloudflare/workers-types"
          - "@cloudflare/kv-asset-handler"
        update-types:
          - "patch"
      dev-tools-patch:
        patterns:
          - "wrangler"
          - "esbuild"
          - "vitest"
          - "typescript"
          - "@typescript-eslint/*"
          - "eslint*"
        update-types:
          - "patch"
      dev-tools-minor:
        patterns:
          - "vitest"
          - "typescript"
          - "@typescript-eslint/*"
          - "eslint*"
        update-types:
          - "minor"
    # Never auto-open PRs for wrangler major bumps — require manual action
    ignore:
      - dependency-name: "wrangler"
        update-types:
          - "version-update:semver-major"
          - "version-update:semver-minor"
    labels:
      - "dependabot"
      - "dependencies"
    commit-message:
      prefix: "chore"
      prefix-development: "chore"
    open-pull-requests-limit: 10
```

The `groups` key collapses related patch bumps into a single PR, cutting weekly PR volume
dramatically for large Workers projects. Minor bumps for `wrangler` are explicitly excluded
because Wrangler minor versions frequently introduce breaking CLI changes.

## Section 2: Auto-Merge Workflow with Tiered Safety Gates

```yaml
# .github/workflows/dependabot-auto-merge.yml
name: Dependabot Auto-Merge

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]

permissions:
  contents: write
  pull-requests: write

jobs:
  classify:
    if: github.actor == 'dependabot[bot]'
    runs-on: ubuntu-latest
    outputs:
      merge_tier: ${{ steps.classify.outputs.tier }}
      update_type: ${{ steps.classify.outputs.update_type }}
    steps:
      - name: Fetch Dependabot metadata
        id: meta
        uses: dependabot/fetch-metadata@v2
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}

      - name: Classify merge tier
        id: classify
        env:
          DEPENDENCY_NAMES: ${{ steps.meta.outputs.dependency-names }}
          UPDATE_TYPE: ${{ steps.meta.outputs.update-type }}
          PACKAGE_ECOSYSTEM: ${{ steps.meta.outputs.package-ecosystem }}
        run: |
          UPDATE_TYPE="${UPDATE_TYPE}"
          echo "update_type=${UPDATE_TYPE}" >> "$GITHUB_OUTPUT"

          # Tier A — always auto-merge: dev-only patch bumps (non-wrangler)
          if [[ "$UPDATE_TYPE" == "version-update:semver-patch" ]]; then
            # Check if wrangler is in the dependency list — never auto-merge wrangler
            if echo "$DEPENDENCY_NAMES" | grep -qw "wrangler"; then
              echo "tier=manual" >> "$GITHUB_OUTPUT"
              echo "Wrangler patch — requires manual review"
            elif echo "$DEPENDENCY_NAMES" | grep -qE "hono|itty-router|@cloudflare/"; then
              echo "tier=runtime-patch" >> "$GITHUB_OUTPUT"
            else
              echo "tier=devtools-patch" >> "$GITHUB_OUTPUT"
            fi
          elif [[ "$UPDATE_TYPE" == "version-update:semver-minor" ]]; then
            if echo "$DEPENDENCY_NAMES" | grep -qE "hono|itty-router|@cloudflare/"; then
              echo "tier=runtime-minor" >> "$GITHUB_OUTPUT"
            else
              echo "tier=devtools-minor" >> "$GITHUB_OUTPUT"
            fi
          else
            echo "tier=manual" >> "$GITHUB_OUTPUT"
          fi

  # Tier: dev-tools patch — auto-merge after CI passes
  auto-merge-devtools-patch:
    needs: classify
    if: needs.classify.outputs.merge_tier == 'devtools-patch'
    runs-on: ubuntu-latest
    steps:
      - name: Wait for required checks
        # Let CI start — the merge queue will enforce required checks
        run: echo "Proceeding to enable auto-merge for dev-tools patch"

      - name: Enable auto-merge
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh pr merge --auto --squash "${{ github.event.pull_request.number }}" \
            --repo "${{ github.repository }}"

  # Tier: runtime patch — auto-merge only after integration tests pass
  auto-merge-runtime-patch:
    needs: classify
    if: needs.classify.outputs.merge_tier == 'runtime-patch'
    runs-on: ubuntu-latest
    steps:
      - name: Enable auto-merge (requires integration gate)
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh pr merge --auto --squash "${{ github.event.pull_request.number }}" \
            --repo "${{ github.repository }}"
        # The branch protection rule requires `integration / workers-e2e` to pass
        # before the auto-merge actually fires.

  # Tier: minor or major — request human review
  request-review:
    needs: classify
    if: |
      needs.classify.outputs.merge_tier == 'manual' ||
      needs.classify.outputs.merge_tier == 'runtime-minor' ||
      needs.classify.outputs.merge_tier == 'devtools-minor'
    runs-on: ubuntu-latest
    steps:
      - name: Add label for human triage
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          TIER="${{ needs.classify.outputs.merge_tier }}"
          gh pr edit "${{ github.event.pull_request.number }}" \
            --add-label "needs-human-review,${TIER}" \
            --repo "${{ github.repository }}"

      - name: Comment with context
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh pr comment "${{ github.event.pull_request.number }}" \
            --repo "${{ github.repository }}" \
            --body "**Auto-merge skipped** — tier: \`${{ needs.classify.outputs.merge_tier }}\`.
          Update type: \`${{ needs.classify.outputs.update_type }}\`.
          Please review manually before merging."
```

## Section 3: Branch Protection Rules to Back the Merge Policy

Branch protection must be configured so that `auto-merge` cannot circumvent integration tests.
Without this, a Worker runtime package could slip through on CI green from unit tests alone.

```yaml
# Terraform (or GitHub API) branch protection rule — main branch
resource "github_branch_protection" "main" {
  repository_id = github_repository.workers_app.node_id
  pattern       = "main"

  required_status_checks {
    strict = true
    contexts = [
      "ci / unit-tests",
      "ci / type-check",
      "integration / workers-e2e",   # Miniflare/Vitest integration suite
      "integration / wrangler-dry-run",  # Ensures wrangler.toml is parseable
    ]
  }

  required_pull_request_reviews {
    dismiss_stale_reviews           = true
    require_code_owner_reviews      = false  # Not required for Dependabot auto-merge
    required_approving_review_count = 0      # 0 allows auto-merge without human approval
                                             # for patch-tier after CI passes
  }

  # For runtime-minor and above, a code owner review is enforced via CODEOWNERS
  # on the package.json and wrangler.toml files.
  allow_auto_merge = true
  delete_branch_on_merge = true
}
```

`CODEOWNERS` entry that adds a human gate for `package.json` changes touching runtime packages:

```
# .github/CODEOWNERS
# Any change to runtime deps requires a Workers team member review
package.json         @org/workers-core
wrangler.toml        @org/workers-core
packages/*/package.json  @org/workers-core
```

For Dependabot PRs in the `devtools-patch` tier, the `required_approving_review_count = 0`
setting in branch protection, combined with `auto-merge`, means CI green → merge. For
`runtime-patch` the CODEOWNERS rule kicks in and requires a review approval unless bypassed
by a org-level bypass list.

## Anti-patterns

- **Auto-merging `wrangler` minor/major without a staging deploy** — Wrangler 3→4 changed
  `wrangler publish` to `wrangler deploy` and altered secret-handling flags. Auto-merging
  this breaks CI pipelines silently.
- **Setting `open-pull-requests-limit` too high** — 20+ open Dependabot PRs leads to constant
  rebase conflicts and wasted CI minutes. Keep it at 10 or below and use `groups`.
- **No cooldown on security updates** — do NOT add `wrangler` or `@cloudflare/workers-types`
  to the security-updates ignore list. Security patches in runtime packages should never be
  blocked, even if minor versions are gated.
- **Using `--merge` instead of `--squash`** — merge commits from Dependabot clutter the git
  history. Use `--squash` to keep the history linear.
- **Enabling auto-merge without required status checks** — if branch protection has zero
  required checks, `auto-merge` fires immediately on PR open. Always pair auto-merge with
  at least `unit-tests` and `wrangler-dry-run` as required checks.

## Gotchas

- **`dependabot[bot]` cannot approve its own PRs** — if your branch protection requires at
  least 1 approval, you need a second GitHub App or a `DEPENDABOT_TOKEN` PAT with write access
  to call `gh pr review --approve`. Never use `GITHUB_TOKEN` for self-approval; it is blocked.
- **Grouped PRs reset on any manual push** — if you push a commit to a Dependabot grouped PR
  branch, Dependabot will close and re-open it, wiping your review. Do not modify Dependabot
  branches directly.
- **Auto-merge requires the feature to be enabled repo-wide** — `Settings → General → Allow
  auto-merge` must be checked. Org-level enforcement is not available; each repo needs it on.
- **`fetch-metadata` action requires the PR to be from `dependabot[bot]`** — if a developer
  creates a PR named like a Dependabot PR, the actor check (`if: github.actor == 'dependabot[bot]'`)
  prevents accidental auto-merge.
- **`wrangler.toml` binding changes are not caught by `npm update`** — a Dependabot PR for
  `@cloudflare/workers-types` may introduce new binding type definitions that conflict with
  your existing `wrangler.toml`. The `wrangler-dry-run` required check catches this.

## Verification

```bash
# Check auto-merge is enabled on the repository
gh api repos/{owner}/{repo} --jq '.allow_auto_merge'
# → true

# List open Dependabot PRs and their auto-merge state
gh pr list --author "dependabot[bot]" \
  --json number,title,autoMergeRequest \
  --jq '.[] | "\(.number) \(.title) auto-merge=\(.autoMergeRequest != null)"'

# Verify required checks are enforced on main
gh api repos/{owner}/{repo}/branches/main \
  --jq '.protection.required_status_checks.contexts'

# Simulate a Dependabot PR classification locally
export DEPENDENCY_NAMES="hono"
export UPDATE_TYPE="version-update:semver-patch"
# Run the classify step from the workflow script manually and inspect output.

# After a merge, verify the Worker still deploys to the staging environment
wrangler deploy --env staging --dry-run
```

## Related

- `github-auto-merge.md` — generic auto-merge configuration for any PR type
- `dependabot-config.md` — full Dependabot configuration reference
- `dependabot-vs-renovate-2026.md` — comparison of Dependabot and Renovate for Workers projects
- `github-actions-oidc-cloudflare-deploy.md` — OIDC-based deploy workflow that runs as a required check
- `github-branch-protection-merge-queue.md` — merge queue as an alternative to auto-merge
- `github-dependabot-cooldown-security-boundary.md` — cooldown periods for security updates

## Sources

- https://docs.github.com/en/code-security/dependabot/working-with-dependabot/automating-dependabot-with-github-actions
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-auto-merge-for-pull-requests-in-your-repository
- https://github.com/dependabot/fetch-metadata
- https://developers.cloudflare.com/workers/wrangler/migration/
- https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
