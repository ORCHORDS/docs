# GitHub Required Status Checks for Workers CI

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
PRs are merging to your Workers repo without TypeScript type errors, failing tests, or broken Wrangler configs being caught first. You need GitHub branch protection to enforce that specific CI status checks — typecheck, unit tests, and a Wrangler dry-run — all pass before any PR can merge, and you want the merge queue to work without manual re-runs.

---

## Context
GitHub branch protection rules support "required status checks" — named CI jobs that must report success before a PR can be merged. For a Workers project, the most valuable gates are TypeScript type checking (`wrangler-typecheck`), unit tests (`vitest`), and a Wrangler deploy dry-run (`wrangler-dry-run`) that validates `wrangler.toml` and bundle output without pushing to Cloudflare. The `merge_group` trigger ensures checks re-run when a PR enters the merge queue, preventing races. Dependabot PRs can bypass these checks via the branch protection bypass list so security updates aren't blocked by flaky CI.

---

## Setup / Config

```yaml
# .github/workflows/workers-ci.yml
# Job names here become the status check names referenced in branch protection
name: Workers CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  merge_group:           # Required for GitHub merge queue support
    branches: [main]

env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

jobs:
  # Status check name: "wrangler-typecheck"
  wrangler-typecheck:
    name: wrangler-typecheck
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - name: Run TypeScript typecheck
        run: npx tsc --noEmit

  # Status check name: "vitest"
  vitest:
    name: vitest
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - name: Run unit tests
        run: npx vitest run --reporter=verbose

  # Status check name: "wrangler-dry-run"
  wrangler-dry-run:
    name: wrangler-dry-run
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
      - run: npm ci
      - name: Wrangler deploy dry-run
        run: npx wrangler deploy --dry-run --env production
```

---

## Implementation

```yaml
# Branch protection API payload
# Apply with: gh api --method PUT /repos/example-org/example-repo/branches/main/protection
# (Requires admin access or a PAT with repo scope)
{
  "required_status_checks": {
    "strict": true,
    "checks": [
      { "context": "wrangler-typecheck" },
      { "context": "vitest" },
      { "context": "wrangler-dry-run" }
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "required_approving_review_count": 1,
    "bypass_pull_request_allowances": {
      "apps": ["dependabot"],
      "users": [],
      "teams": []
    }
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
```

```yaml
# Merge queue configuration (Settings > Rules > Merge Queue or Rulesets)
# Enable via GitHub UI: Settings > Branches > Edit rule > Require merge queue
# Or via GitHub Rulesets API:
{
  "name": "main merge queue",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/main"],
      "exclude": []
    }
  },
  "rules": [
    {
      "type": "merge_queue",
      "parameters": {
        "check_response_timeout_minutes": 10,
        "min_entries_to_merge": 1,
        "max_entries_to_merge": 5,
        "merge_method": "SQUASH",
        "grouping_strategy": "ALLGREEN"
      }
    }
  ]
}
```

```yaml
# .github/workflows/dependabot-automerge.yml
# Auto-merge Dependabot patch/minor PRs that pass CI
name: Dependabot Auto-merge

on:
  pull_request:
    branches: [main]

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

      - name: Auto-merge patch and minor updates
        if: >
          steps.meta.outputs.update-type == 'version-update:semver-patch' ||
          steps.meta.outputs.update-type == 'version-update:semver-minor'
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          PR_URL: ${{ github.event.pull_request.html_url }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## Integration / Testing

```bash
# Verify branch protection is configured (requires admin access)
gh api /repos/example-org/example-repo/branches/main/protection \
  --jq '.required_status_checks.checks[].context'
# Expected output:
# wrangler-typecheck
# vitest
# wrangler-dry-run

# Check strict mode (require branch to be up-to-date before merging)
gh api /repos/example-org/example-repo/branches/main/protection \
  --jq '.required_status_checks.strict'
# Expected: true

# List recent CI runs to confirm all three checks ran
gh run list --workflow workers-ci.yml --limit 10 \
  --json conclusion,name,event \
  --jq '.[] | select(.event == "pull_request") | { name, conclusion }'

# Confirm merge_group event trigger works (open a PR and add to merge queue)
gh pr create --base main --head feature/test-merge-queue \
  --title "test: merge queue status check validation" \
  --body "Validates that wrangler-typecheck, vitest, wrangler-dry-run run on merge_group trigger"

# Force push a typecheck error and confirm protection blocks the merge
# (modify a .ts file with a type error, push, observe PR blocked)

# Verify Dependabot bypass is working
gh api /repos/example-org/example-repo/branches/main/protection \
  --jq '.required_pull_request_reviews.bypass_pull_request_allowances.apps'
# Expected: ["dependabot"]
```

---

## Anti-patterns
- **Using job `id` instead of job `name` as the status check context** — GitHub registers the status check under the job's `name` field (or the workflow job key if `name` is omitted). Mismatch between the branch protection context string and the actual job name means the check never satisfies the requirement.
- **No `merge_group` trigger** — Without it, PRs entering the merge queue skip CI re-validation. A PR that passed CI against an older base may fail against the current main.
- **Blocking Dependabot with CODEOWNERS and status checks** — Dependabot PRs need either bypass allowances or an auto-merge workflow; blocking both means security updates pile up unmerged.
- **`strict: false` on required checks** — Without strict mode, a PR that passed CI against a stale base can be merged even if a concurrent merge introduced a regression. Always set `strict: true` for production branches.
- **Referencing `wrangler deploy` output names** — Wrangler's terminal output is not a GitHub status check; only GitHub Actions job names become status checks. Don't try to reference Wrangler CLI output strings in branch protection.

---

## Gotchas
- Status check names are case-sensitive in branch protection; `Vitest` and `vitest` are treated as different checks.
- If you rename a job in the workflow YAML, the old status check name becomes "stale" in branch protection — GitHub won't auto-update the protection rule, and PRs will be permanently blocked until you manually update the branch protection rule to use the new name.
- The `merge_group` event is only available if merge queues are enabled for the repository; enabling it in the workflow without enabling the feature in Settings has no effect.
- `--dry-run` with `wrangler deploy` still requires a valid `CLOUDFLARE_API_TOKEN` to resolve bindings metadata from Cloudflare's API, even though it doesn't deploy.
- Required status checks only apply to PRs targeting the protected branch; direct pushes to `main` by admins bypass checks unless `enforce_admins: true` is set.

---

## Verification

```bash
# Full branch protection summary
gh api /repos/example-org/example-repo/branches/main/protection \
  --jq '{
    required_checks: .required_status_checks.checks[].context,
    strict: .required_status_checks.strict,
    codeowners_required: .required_pull_request_reviews.require_code_owner_reviews,
    dismiss_stale: .required_pull_request_reviews.dismiss_stale_reviews,
    force_push_allowed: .allow_force_pushes.enabled,
    deletions_allowed: .allow_deletions.enabled
  }'

# Confirm all three checks appear as required on an open PR
gh pr checks <pr-number> --required
# Expected: wrangler-typecheck, vitest, wrangler-dry-run all listed as required

# Confirm merge is blocked when a check fails
gh pr view <pr-number> --json mergeStateStatus \
  --jq '.mergeStateStatus'
# Expected: BLOCKED (when any required check is failing)
# Expected: MERGEABLE (when all pass and review approved)
```

---

## Related
- `github-codeowners-workers-monorepo.md`
- `github-actions-d1-migration-ci.md`
- `github-release-automated-changelog.md`
- `github-actions-node-modules-cache-workers.md`

---

## Sources
- GitHub Branch Protection Documentation — https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- GitHub Merge Queue Documentation — https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/incorporating-changes-from-a-pull-request/merging-a-pull-request-with-a-merge-queue
- Wrangler Deploy Dry-run — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- dependabot/fetch-metadata Action — https://github.com/dependabot/fetch-metadata
