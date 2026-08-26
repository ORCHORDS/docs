# Branch Strategy for Multi-Environment Deployment

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

The team has three environments — development, staging, and production — and no
consistent answer to "which branch maps to which environment?" Some engineers push
directly to `main` (which deploys to staging); others push to `develop`. Nobody
is certain whether the staging environment reflects what production will look like
after the next release. Hotfixes go directly to `main` but never make it back to
`develop`. The environments drift apart over weeks.

A multi-environment branch strategy makes the mapping explicit, deterministic, and
automated: every merge to a branch triggers a deployment to exactly one environment,
and the flow of code between environments is unambiguous.

---

## Context

Multi-environment strategies sit on a spectrum. The choice of model depends on
three factors:

1. **Deployment frequency**: how often does code go to production?
2. **Environment count**: how many named stages exist?
3. **Team discipline**: can the team maintain multiple long-lived branches?

| Model | Deploys/week | Long-lived branches | Best for |
|---|---|---|---|
| Trunk-based (env via tags) | 5–50 | 1 (`main`) | High-frequency, mature CI |
| GitFlow-derived (env per branch) | 1–5 | 3–4 | Regulated releases |
| Environment promotion (per-env branches) | 2–10 | 2–3 | SaaS with staged rollout |
| Branch-per-environment + merge queue | 5–20 | 2 | Cloud-native, preview URLs |

This article documents the **environment-promotion model** (the most common
practical choice for teams with 5–50 engineers), then covers trunk-based env
routing via tags for high-frequency shops.

---

## Model 1 — Environment Promotion Branches

### Branch → Environment mapping

```
main  ──→  [CI] ──→  production
  ↑
staging  ──→  [CI] ──→  staging environment
  ↑
develop  ──→  [CI] ──→  development environment
  ↑
feature/*  ──→  [CI] ──→  PR preview environment (ephemeral)
```

All feature branches are cut from `develop`. When a feature is reviewed and approved,
it is merged to `develop`. Periodically (daily or on a release cadence), `develop` is
promoted to `staging` via a PR. After QA sign-off, `staging` is promoted to `main`,
which deploys to production.

### Branch protection configuration

```bash
# develop: requires CI, one approval, no direct push from most engineers
gh api --method PUT "/repos/org/repo/branches/develop/protection" \
  --field required_status_checks='{"strict":true,"contexts":["ci/test","ci/lint"]}' \
  --field required_pull_request_reviews='{"required_approving_review_count":1}' \
  --field enforce_admins=false \
  --field restrictions=null

# staging: requires CI, two approvals, must come from develop (enforced by convention + CODEOWNERS)
gh api --method PUT "/repos/org/repo/branches/staging/protection" \
  --field required_status_checks='{"strict":true,"contexts":["ci/test","ci/lint","ci/e2e"]}' \
  --field required_pull_request_reviews='{"required_approving_review_count":2,"dismiss_stale_reviews":true}' \
  --field enforce_admins=true \
  --field restrictions=null

# main: requires all checks, two approvals, enforce admins
gh api --method PUT "/repos/org/repo/branches/main/protection" \
  --field required_status_checks='{"strict":true,"contexts":["ci/test","ci/lint","ci/e2e","ci/security"]}' \
  --field required_pull_request_reviews='{"required_approving_review_count":2,"dismiss_stale_reviews":true}' \
  --field enforce_admins=true \
  --field restrictions=null
```

### Automated promotion workflow

```yaml
# .github/workflows/promote-to-staging.yml
name: Promote develop → staging

on:
  # Scheduled promotion: every weekday at 14:00 UTC
  schedule:
    - cron: '0 14 * * 1-5'
  # Manual promotion
  workflow_dispatch:
    inputs:
      reason:
        description: 'Reason for manual promotion'
        required: true

permissions:
  contents: write
  pull-requests: write

jobs:
  promote:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Check develop is ahead of staging
        id: ahead
        run: |
          AHEAD=$(git rev-list --count origin/staging..origin/develop)
          echo "commits_ahead=$AHEAD" >> "$GITHUB_OUTPUT"
          if [[ "$AHEAD" -eq 0 ]]; then
            echo "Nothing to promote. develop == staging."
            exit 0
          fi

      - name: Open promotion PR
        if: steps.ahead.outputs.commits_ahead != '0'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          COMMITS=$(git log --oneline origin/staging..origin/develop | head -20)
          gh pr create \
            --base staging \
            --head develop \
            --title "chore: promote develop → staging $(date -u +%Y-%m-%d)" \
            --body "## Automated promotion\n\n### Commits included\n\`\`\`\n${COMMITS}\n\`\`\`\n\nReviewer: confirm staging deploy health after merge." \
            --label "promotion"
```

---

## Model 2 — Trunk-Based with Environment Routing via Tags and Workflows

In high-frequency shops, long-lived `develop` and `staging` branches create merge
overhead. Instead, every merge to `main` deploys to a "dev" environment. Production
deployments are triggered by version tags.

```
feature/* ──→ main ──→ CI ──→ dev.example.com  (always)
                              ↓
                        git tag v1.2.3 ──→ CI ──→ staging.example.com
                                              ↓
                                       Manual approval ──→ production
```

### Workflow that routes by ref type

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]
    tags: ['v[0-9]+.[0-9]+.[0-9]+']

jobs:
  deploy-dev:
    if: github.ref_type == 'branch' && github.ref_name == 'main'
    runs-on: ubuntu-latest
    environment:
      name: development
      url: https://dev.example.com
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to dev
        run: ./scripts/deploy.sh --env dev

  deploy-staging:
    if: github.ref_type == 'tag'
    runs-on: ubuntu-latest
    environment:
      name: staging
      url: https://staging.example.com
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to staging
        run: ./scripts/deploy.sh --env staging --version "${{ github.ref_name }}"

  deploy-production:
    if: github.ref_type == 'tag'
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment:
      name: production   # configured with required-reviewers in GitHub Settings
      url: https://example.com
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to production
        run: ./scripts/deploy.sh --env production --version "${{ github.ref_name }}"
```

The `environment: production` block in GitHub Actions triggers a manual approval
gate if the environment is configured with required reviewers in the repository
settings — no additional tooling needed.

---

## Hotfix Routing

Hotfixes must bypass the normal promotion chain to reach production quickly without
dragging untested `develop` changes along.

```bash
# 1. Cut the hotfix branch from the production ref (main or the release tag)
git checkout -b hotfix/null-payment-crash main

# 2. Apply the fix
#    ... make changes ...

# 3. Open PR directly to main (bypasses develop and staging)
gh pr create --base main --head hotfix/null-payment-crash \
  --label "hotfix" \
  --title "fix: null payment crash in processor (#912)"

# 4. After merge to main and deploy, back-merge to develop and staging
git checkout develop
git merge main --no-ff -m "chore: back-merge hotfix/null-payment-crash from main"
git push origin develop

# OR use a GitHub Action triggered on hotfix label merge:
```

```yaml
# .github/workflows/hotfix-backmerge.yml
name: Backmerge hotfix to develop

on:
  pull_request:
    types: [closed]
    branches: [main]

jobs:
  backmerge:
    if: |
      github.event.pull_request.merged == true &&
      contains(github.event.pull_request.labels.*.name, 'hotfix')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Backmerge to develop
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git fetch origin
          git checkout develop
          git merge origin/main --no-ff \
            -m "chore: backmerge hotfix ${{ github.event.pull_request.title }}"
          git push origin develop
```

---

## Anti-patterns

**Three-way divergence.** `develop`, `staging`, and `main` all have independent
commits. A merge from `develop` → `staging` then requires a separate merge conflict
resolution from `staging` → `main`. The rule: only merge "forward" (develop →
staging → main), never commit directly on `staging` or `main`.

**Environment-specific code.** Code that conditionally behaves differently per
environment based on `process.env.NODE_ENV === 'staging'` is a deployment smell.
Environment differences should be configuration (env vars, feature flags), not
code branches.

**Never merging back from main to develop.** Hotfixes that go directly to `main`
without a back-merge cause `develop` to be behind `main`. Within a sprint this is
fine; over months it creates significant divergence that is painful to reconcile.
Automate the back-merge via the workflow above.

**Too many long-lived environments.** Each environment is a human-maintained surface.
More than 3–4 named environments (dev / staging / pre-prod / prod) creates drift
faster than teams can manage. Replace pre-prod with ephemeral PR preview environments
instead.

---

## Gotchas

- GitHub `environment: production` approvals require the environment to be configured
  in repository settings under **Settings → Environments**. The YAML alone does not
  create the environment — go configure required reviewers.

- Scheduled promotion workflows may race with late PRs merging to `develop`. Guard
  with a status check: the promotion PR fails to merge if `develop` CI is red at
  time of promotion.

- Back-merges from `main` to `develop` can conflict if `develop` has been rebased or
  if squash-merge is the default strategy for `main`. If using squash-merge to `main`,
  cherry-pick hotfixes to `develop` rather than back-merging the full history.

- Tagging strategies for trunk-based environments: tags must be annotated (`git tag -a
  v1.2.3 -m "v1.2.3"`) to carry a tagger identity and timestamp. Lightweight tags are
  fine for CI triggers but lack the audit trail of annotated tags.

---

## Verification

```bash
# Confirm branch → environment mapping is documented
cat .github/ENVIRONMENTS.md  # or wherever your team documents this

# Check which commits are in staging but not in main
git log --oneline origin/main..origin/staging

# Check which commits are in develop but not in staging
git log --oneline origin/staging..origin/develop

# Verify environment protection is configured
gh api "/repos/org/repo/environments" --jq '.[].name'
gh api "/repos/org/repo/environments/production" \
  --jq '{protection_rules: .protection_rules}'

# Confirm the hotfix back-merge workflow is enabled
gh workflow list | grep backmerge
```

---

## Related

- `hotfix-process.md` — detailed hotfix procedure
- `branch-strategies-2026.md` — broader branch model comparison
- `release-branch-strategy-gitflow-trunk.md` — GitFlow vs trunk tradeoffs
- `canary-deployment-strategy.md` — production routing strategies once code reaches main
- `feature-flags-2026.md` — decouple deployment from release to reduce environment count

---

## Sources

- GitHub Actions environments: https://docs.github.com/en/actions/deployment/targeting-different-environments
- GitFlow original proposal: https://nvie.com/posts/a-successful-git-branching-model/
- Trunk Based Development: https://trunkbaseddevelopment.com
- "Continuous Delivery" by Jez Humble & David Farley — environment promotion patterns
