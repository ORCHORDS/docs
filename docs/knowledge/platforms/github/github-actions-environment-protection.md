# github-actions-environment-protection

**Issue:** Configuring GitHub Environments with required reviewers, wait timers, and branch restrictions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Production deployments run without human sign-off. Any branch can deploy to prod. Teams need approval gates, deployment windows, and audit trails baked into the workflow.

## Pattern / Solution
GitHub Environments (Settings → Environments) attach protection rules to a logical target name. A workflow job that declares `environment: production` must pass all rules before the runner starts.

**Workflow side:**
```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://example.com   # shown in the deployment panel
    steps:
      - uses: actions/checkout@v4
      - run: ./scripts/deploy.sh
```

**Environment rules (configured in UI or via API):**
- **Required reviewers** — up to 6 people/teams must approve; the job is queued until approved or rejected
- **Wait timer** — minimum minutes before job starts after trigger (useful for canary bake time)
- **Deployment branches** — restrict which branches/tags can deploy to this environment (e.g., only `main`)

**API-driven environment creation:**
```bash
gh api repos/{owner}/{repo}/environments/production \
  --method PUT \
  --field wait_timer=5 \
  --field 'reviewers[][type]=User' \
  --field 'reviewers[][id]=12345'
```

**Checking deployment status programmatically:**
```bash
gh run list --workflow=deploy.yml --branch=main --limit=5
```

## Gotchas
- Environment protection rules only apply to jobs — not to `on:` triggers. A `push` can still start a workflow; the job just pauses at the environment gate
- If a reviewer rejects, the job fails and cannot be retried without re-triggering the workflow
- `environment:` on a job prevents the job from running in a fork PR by default (fork PRs don't have environment access)
- Free plans can use environments but required reviewers is a paid-plan feature for private repos
- The `url:` field accepts `${{ steps.deploy.outputs.url }}` for dynamic URLs

## Related
- `github-actions-secrets-management.md`
- `github-environments-approval-gates.md`
- `github-required-status-checks.md`
