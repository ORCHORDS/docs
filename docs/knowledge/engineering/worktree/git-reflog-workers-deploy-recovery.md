# Git Reflog Workers Deploy Recovery

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A developer runs `wrangler deploy` from the wrong branch—or after an accidental `git reset`—and an outdated or broken commit is now live in production.
Git reflog lets you pinpoint the exact commit that was deployed, recover the correct state, and redeploy with confidence.

## Context
Wrangler bundles and deploys whatever is in the current working tree at deploy time; it does not record which git commit was used.
The only ground truth for "what was deployed" is either the Wrangler deployment log (accessible via `wrangler deployments list`) or the git reflog, which tracks every HEAD movement on the developer's machine.
Combining `git reflog` with `wrangler deployments` gives a complete recovery workflow: identify the bad deploy, find the correct commit, restore, and redeploy.

---

## Setup — Enable Reflog-Friendly Practices

Record deploy commit SHAs as part of your deploy script so recovery is trivial:

```bash
#!/usr/bin/env bash
# scripts/deploy-with-log.sh <environment>
set -euo pipefail

ENV="${1:-production}"
COMMIT=$(git rev-parse HEAD)
BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "Deploying commit $COMMIT (branch: $BRANCH) to $ENV at $TIMESTAMP"

# Abort if working tree is dirty
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: Working tree has uncommitted changes. Stash or commit before deploying."
  exit 1
fi

# Tag the deploy commit for easy recovery
git tag -f "deploy/$ENV/$(date -u +%Y%m%dT%H%M%S)" HEAD

npx wrangler deploy --env "$ENV"
echo "Deploy complete: $COMMIT → $ENV"
```

---

## Section 1 — Identify What Was Deployed

When an incident hits, the first step is correlating the Wrangler deployment with a git commit:

```bash
# 1. List recent Wrangler deployments (most recent first)
npx wrangler deployments list --env production

# Example output:
# Deployment ID                           Created                   Status
# xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx   2026-08-23T14:30:00.000Z  Active
# yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy   2026-08-22T10:00:00.000Z  Inactive

# 2. Inspect a specific deployment to see its upload metadata
npx wrangler deployments view <deployment-id> --env production

# 3. On the developer's machine: find recent HEAD positions
git reflog --date=iso | head -20

# Example output:
# abc1234 HEAD@{2026-08-23 14:29:45 +0000}: checkout: moving from main to feature/bad-branch
# def5678 HEAD@{2026-08-23 14:00:00 +0000}: pull: Fast-forward
# ghi9012 HEAD@{2026-08-22 10:00:00 +0000}: commit: fix: auth token validation

# 4. Find HEAD state at deploy time (cross-reference timestamps)
git reflog --date=iso | grep "2026-08-23 14:2"
```

---

## Section 2 — Recover the Correct Commit and Redeploy

Once you know which commit should have been deployed, restore it and redeploy:

```bash
# Scenario A: You deployed from the wrong branch and need to redeploy from main
git fetch origin
git checkout main
git pull --ff-only origin main

# Verify you're on the right commit
git log --oneline -5
git show HEAD --stat

# Redeploy from the correct commit
npx wrangler deploy --env production
```

```bash
# Scenario B: An accidental git reset discarded the commit you wanted to deploy.
# Use reflog to find and restore it.

# Find the commit that was live before the reset
git reflog --date=iso | grep -E "commit|merge" | head -10
# > abc1234 HEAD@{2026-08-23 09:55:00 +0000}: commit: feat: new billing endpoint

# Create a recovery branch from the lost commit
git switch -c recovery/billing-hotfix abc1234

# Verify this is the commit you want
git log --oneline -3
git show --stat

# Deploy from the recovery branch
npx wrangler deploy --env production

# Then reconcile with main
git switch main
git merge recovery/billing-hotfix --ff-only
git push origin main
git branch -d recovery/billing-hotfix
```

```bash
# Scenario C: Wrong worktree was used for deploy (deployed feature branch to prod).
# Identify the deploy worktree and its HEAD at deploy time.

# List all worktrees and their current HEADs
git worktree list --porcelain

# Each worktree has its own reflog — specify the worktree's git dir
git --git-dir=../.git/worktrees/<worktree-name> reflog --date=iso | head -10

# Find the last known-good commit on main worktree
git --git-dir=.git reflog show main --date=iso | head -5
```

---

## Section 3 — Automated Deploy-Commit Tagging

Automate the commit-SHA recording in CI so recovery doesn't depend on a local reflog:

```yaml
# .github/workflows/deploy-production.yml (excerpt)
- name: Tag deploy commit
  run: |
    SHA=$(git rev-parse HEAD)
    TAG="deploy/production/$(date -u +%Y%m%dT%H%M%S)"
    git tag "$TAG" "$SHA"
    git push origin "$TAG"
    echo "DEPLOY_TAG=$TAG" >> "$GITHUB_ENV"
    echo "DEPLOY_SHA=$SHA" >> "$GITHUB_ENV"

- name: Deploy to production
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  run: npx wrangler deploy --env production

- name: Record deploy in commit status
  if: always()
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    STATE=$([[ "${{ job.status }}" == "success" ]] && echo "success" || echo "failure")
    gh api repos/${{ github.repository }}/statuses/${{ env.DEPLOY_SHA }} \
      -f state="$STATE" \
      -f context="wrangler/production" \
      -f description="Wrangler deploy $STATE" \
      -f target_url="https://dash.cloudflare.com/workers"
```

Recovery from a CI deploy:

```bash
# Find the last successful production deploy tag
git tag -l 'deploy/production/*' | sort | tail -5

# Check what that commit contains
git show deploy/production/20260823T143000 --stat

# Redeploy that exact commit
git checkout deploy/production/20260823T143000
npx wrangler deploy --env production
git checkout main   # return to main after emergency deploy
```

---

## Anti-patterns

- Running `wrangler deploy` without first checking `git status` and `git branch` — the most common cause of wrong-commit deploys
- Relying solely on Wrangler's deployment history to identify what was deployed — it records upload time but not the source git commit unless you explicitly embed it
- Using `git reset --hard` to undo a bad commit without checking `git status` first — may discard unrelated staged work alongside the bad commit
- Deploying directly from a local machine in emergencies without pushing the commit to remote first — if the local machine is lost, recovery is impossible

## Gotchas

- Git reflog is local: entries exist only on the machine where the commands ran. CI deploys have no reflog — that's why tagging + commit status recording is essential
- `git reflog` entries expire (default 90 days for reachable, 30 days for unreachable). Run `git gc` or `git maintenance run` rarely; it can prune entries needed for recovery
- `git worktree list --porcelain` shows each worktree's HEAD but NOT its reflog inline; you must explicitly pass `--git-dir` to read a worktree's reflog
- After `git checkout <sha>` (detached HEAD), `wrangler deploy` reads the working tree correctly — but `git push` will fail. Always create a branch before pushing recovery changes

## Verification

```bash
# Confirm the correct commit is checked out before deploying
git rev-parse HEAD
git log --oneline -1

# List all deploy tags on remote
git ls-remote --tags origin 'refs/tags/deploy/production/*'

# Verify a Wrangler deployment ID maps to a known deploy window
npx wrangler deployments list --env production --json | \
  jq '.[] | {id: .id, created: .created_on}' | head -5

# Show all local reflog entries in the last hour
git reflog --date=iso | awk -F'@{' '{print $2}' | grep "2026-08-23 14"
```

## Related

- `git-reflog-2026.md`
- `git-reflog-workers-accidental-commit-recovery.md`
- `git-revert-safe-rollback-workers-production.md`
- `wrangler-rollback-git-tag-workflow.md`
- `wrangler-version-upload-deploy-split-workflow.md`
- `git-tag-semantic-versioning-workers-deploy-gates.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#deployments
- https://git-scm.com/docs/git-reflog
- https://git-scm.com/docs/git-worktree
- https://docs.github.com/en/rest/commits/statuses
- https://developers.cloudflare.com/workers/observability/logs/workers-logs/
