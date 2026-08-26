# GitHub CODEOWNERS for Workers Monorepo

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
In a Workers monorepo, PRs touching shared infrastructure files like `wrangler.toml` go through without review from the platform team, and package-specific Workers changes get reviewed by the wrong team. You need a CODEOWNERS file that routes review requests to domain experts automatically and enforces those reviews via branch protection.

---

## Context
GitHub CODEOWNERS automatically requests reviews from designated owners whenever files in their scope are changed in a PR. In a Workers monorepo, this maps neatly to per-package directories (each housing a Worker), shared config files owned by a platform team, and global CI/CD workflows. Branch protection rules can require that at least one CODEOWNERS reviewer approves before merging, ensuring domain experts sign off. Automated dependency PRs from Dependabot or renovate-bot can be exempted from strict CODEOWNERS enforcement by configuring bypass lists on branch protection.

---

## Setup / Config

```
# .github/CODEOWNERS
# Format: <pattern> <owner> [<owner>...]
# Patterns are matched top-to-bottom; last match wins.

# === Global fallback — platform team reviews everything not matched below ===
* @example-org/example-repo

# === Shared infrastructure ===
/wrangler.toml                    @example-org/example-repo
/package.json                     @example-org/example-repo
/package-lock.json                @example-org/example-repo
/.github/                         @example-org/example-repo
/.github/workflows/               @example-org/example-repo

# === Individual Workers packages ===
/packages/api-worker/             @example-org/example-repo
/packages/auth-worker/            @example-org/example-repo @example-org/example-repo
/packages/edge-cache-worker/      @example-org/example-repo
/packages/storefront-worker/      @example-org/example-repo
/packages/webhooks-worker/        @example-org/example-repo

# === Shared libraries ===
/packages/lib-db/                 @example-org/example-repo @example-org/example-repo
/packages/lib-auth/               @example-org/example-repo
/packages/lib-utils/              @example-org/example-repo

# === Docs — any team member can approve ===
/docs/                            @example-org/example-repo
*.md                              @example-org/example-repo
```

---

## Implementation

```yaml
# Branch protection rule — set via GitHub API or UI
# Settings > Branches > Add branch protection rule > branch name: main

# Equivalent GitHub API payload (PATCH /repos/{owner}/{repo}/branches/main/protection)
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["wrangler-typecheck", "vitest", "wrangler-dry-run"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "required_approving_review_count": 1,
    "bypass_pull_request_allowances": {
      "apps": ["dependabot", "renovate"],
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
# .github/workflows/codeowners-check.yml
# Adds a status check that verifies CODEOWNERS syntax is valid
name: CODEOWNERS Lint

on:
  pull_request:
    paths:
      - .github/CODEOWNERS

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate CODEOWNERS
        uses: mszostok/codeowners-validator@v0.7.4
        with:
          checks: "files,syntax,duppatterns"
          experimental_checks: "avoid-shadowing"
          github_access_token: ${{ secrets.GITHUB_TOKEN }}
```

---

## Integration / Testing

```bash
# Verify which teams/users own a file path (uses GitHub CLI)
gh api /repos/example-org/example-repo/codeowners/errors

# List all teams in the orchords org
gh api /orgs/example-org/example-repo --jq '.[].slug'

# Simulate who would be requested for a PR touching api-worker
# (create a test PR via CLI and inspect requested_reviewers)
gh pr create \
  --base main \
  --head feature/test-codeowners \
  --title "Test CODEOWNERS routing" \
  --body "Tests that api-worker changes request backend team"

gh pr view --json requestedReviewers,requestedTeams

# Check branch protection is in place
gh api /repos/example-org/example-repo/branches/main/protection \
  --jq '.required_pull_request_reviews.require_code_owner_reviews'
# Expected: true

# List current CODEOWNERS errors (GitHub validates on push)
gh api /repos/example-org/example-repo/codeowners/errors --jq '.errors'
```

---

## Anti-patterns
- **Single global owner for the entire repo** — `* @one-person` creates a review bottleneck and defeats the purpose of team ownership. Use team slugs and per-directory rules.
- **Listing individuals instead of teams** — Individual usernames require updating CODEOWNERS whenever someone joins or leaves. Use `@org/team-slug` so GitHub team membership drives ownership.
- **Putting CODEOWNERS in repo root** — GitHub only recognises CODEOWNERS in root, `.github/`, or `docs/`. Using `.github/CODEOWNERS` is the cleanest convention for monorepos.
- **No bypass for bots** — Blocking Dependabot PRs on CODEOWNERS approval stalls automated security updates. Add `dependabot` and `renovate` to the bypass list.
- **Overlapping patterns with wrong ordering** — GitHub uses last-match-wins within the file; a broad `*` rule placed after specific rules silently overrides them. Put the global fallback first.

---

## Gotchas
- CODEOWNERS review requests are only auto-added when the PR is opened or re-opened, not when new commits are pushed (unless "dismiss stale reviews" re-triggers requests).
- Teams referenced in CODEOWNERS must be visible to GitHub (not secret) and must have read access to the repository.
- The `require_code_owner_reviews` setting in branch protection only triggers if the PR modifies files that have an owner; files with no matching rule don't require a CODEOWNERS review.
- GitHub limits CODEOWNERS files to 3 MB and 1000 lines; beyond that, ownership is silently ignored.
- Branch protection bypass for Dependabot uses the app name `dependabot`, not the GitHub Actions bot account `github-actions[bot]`.

---

## Verification

```bash
# Confirm CODEOWNERS file is being read (no errors)
gh api /repos/example-org/example-repo/codeowners/errors
# Expected: { "errors": [] }

# Confirm branch protection requires CODEOWNERS review
gh api /repos/example-org/example-repo/branches/main/protection \
  --jq '{
    codeowners: .required_pull_request_reviews.require_code_owner_reviews,
    dismiss_stale: .required_pull_request_reviews.dismiss_stale_reviews,
    required_count: .required_pull_request_reviews.required_approving_review_count
  }'
# Expected: { codeowners: true, dismiss_stale: true, required_count: 1 }
```

---

## Related
- `github-required-status-checks-workers-ci.md`
- `workers-monorepo-wrangler-config.md`
- `github-actions-node-modules-cache-workers.md`

---

## Sources
- GitHub CODEOWNERS Documentation — https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- GitHub Branch Protection API — https://docs.github.com/en/rest/branches/branch-protection
- codeowners-validator Action — https://github.com/mszostok/codeowners-validator
