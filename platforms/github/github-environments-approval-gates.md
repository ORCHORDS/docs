# github-environments-approval-gates

**Issue:** Setting up human approval gates before production deployments using GitHub Environments
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Deployments to production happen automatically without any human review. Teams want a "deploy button" model where a senior engineer must approve before the runner proceeds, with a full audit trail.

## Pattern / Solution
GitHub Environments support "Required reviewers" — up to 6 people or teams who must approve. The job is paused with a notification sent to reviewers.

**Environment configuration (Settings → Environments → production):**
- Required reviewers: add users or teams
- Prevent self-review: optionally disallow the person who triggered the workflow from approving
- Wait timer: e.g., 5 minutes (good for post-deploy canary bake window)
- Deployment branches: restrict to `main` only

**Workflow that triggers the gate:**
```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  deploy-prod:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://example.com
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - run: ./deploy.sh --env production
```

**Approving via `gh` CLI:**
```bash
# List pending deployments
gh run list --workflow=deploy.yml

# Approve (requires review permission on the environment)
gh api repos/OWNER/REPO/actions/runs/RUN_ID/pending_deployments \
  --method POST \
  --field 'environment_ids[]=ENV_ID' \
  --field state=approved \
  --field comment="LGTM, deploy away"
```

**Checking approval status in downstream logic:**
```yaml
      - name: Post-approval audit log
        run: |
          echo "Approved by: ${{ github.actor }}"
          echo "Deployment to: ${{ github.event.deployment.environment }}"
```

## Gotchas
- Required reviewers is a paid feature for private repos (included in Team and Enterprise plans)
- A reviewer must have at least Read access to the repo and be explicitly added to the environment's reviewer list — org-wide admin access alone doesn't bypass the gate
- If no reviewer acts within 30 days the deployment times out and fails
- "Prevent self-review" does not prevent the triggering user from being a reviewer for a different person's run — it only stops them from reviewing their own run
- Deployment environment names are case-sensitive in the workflow `environment:` key

## Related
- `github-actions-environment-protection.md`
- `github-required-status-checks.md`
- `github-merge-queue.md`
