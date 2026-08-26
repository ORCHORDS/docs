# git revert Safe Production Rollback for Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A Cloudflare Worker deployment introduces a regression — elevated 5xx error rates, broken KV reads, or a D1 query timeout — and the on-call engineer needs to restore the previous behaviour within the SLO's error budget window. `wrangler rollback` can revert to the previous upload, but it operates outside version control, creating a gap between what git says is deployed and what Cloudflare is running. `git revert` creates a proper inverse commit, keeps the history clean, triggers CI/CD validations, and ensures the next deploy from `main` does not re-introduce the regression.

---

## Context

`git revert <commit>` creates a new commit that is the exact inverse of the target commit. Unlike `git reset`, it never rewrites history, making it safe on protected branches. For Cloudflare Workers teams using trunk-based development, a revert commit on `main` immediately triggers the GitHub Actions Wrangler deploy pipeline, restoring the previous Worker state with full auditability.

This differs from `wrangler rollback` (which reverts the Cloudflare-side upload without a git commit) and from `git reset --hard` (which rewrites history and is unsafe on shared branches).

---

## Anatomy of a Safe Revert

```bash
# 1. Identify the bad commit on main
git log --oneline -10 origin/main

# Example:
# a1b2c3d feat(auth-worker): add token refresh endpoint
# 9f8e7d6 chore(deps): bump wrangler to 3.80.0    <-- probably fine
# 3c4d5e6 feat(kv): add rate-limit namespace binding  <-- suspect

# 2. Revert the suspect commit
git revert 3c4d5e6 --no-edit

# --no-edit uses the default revert message: "Revert 'feat(kv): ...'"
# Produces a new commit: "Revert 'feat(kv): add rate-limit namespace binding'"

# 3. Push to main (or PR branch depending on branch protection)
git push origin main
```

The push triggers CI, which runs `wrangler deploy`, restoring the previous Worker behaviour.

---

## Reverting a Merge Commit

Deployments sometimes land via a squash-merge or a merge commit. Reverting a merge commit requires specifying the mainline parent:

```bash
# Find the merge commit
git log --oneline --merges -5 origin/main

# Revert the merge commit; -m 1 keeps the mainline (main branch) as parent
git revert -m 1 <merge-commit-hash> --no-edit

# Verify what changed
git diff HEAD~1 HEAD --stat
```

---

## Reverting Multiple Commits (Regression Window)

If the regression spans multiple commits (e.g., a feature was deployed across two PRs), revert them in reverse order:

```bash
# Commits to revert (newest first):
# d4e5f6a feat(auth-worker): wire token refresh to KV
# 3c4d5e6 feat(kv): add rate-limit namespace binding

git revert d4e5f6a --no-edit
git revert 3c4d5e6 --no-edit

# Or, revert a range (also newest-first):
# git revert d4e5f6a..HEAD is NOT what you want — it reverts commits AFTER d4e5f6a
# Use explicit hashes or the range below:
git revert --no-edit 3c4d5e6^..d4e5f6a
# This reverts commits from 3c4d5e6 to d4e5f6a inclusive, newest first
```

---

## Pairing git revert with wrangler rollback During the Incident

When the SLO breach is immediate and CI pipeline duration (typically 2–5 minutes) is too slow:

```bash
# Step 1 (immediate): Roll back the Cloudflare-side deployment
npx wrangler rollback --env production --message "P0 incident rollback — see GH issue #<number>"

# Step 2 (within 15 minutes): Create the git revert to restore source truth
git revert <bad-commit> --no-edit
git push origin main
# CI runs, confirms parity, re-deploys the reverted code
```

After CI deploys the reverted code, `wrangler deployments list` should show the CI-deployed version as the active one, replacing the manual rollback.

---

## D1 Schema Revert Considerations

`git revert` does not automatically undo D1 migrations. If the reverted commit included a new D1 migration, you must:

1. Revert the migration file addition in git (`git revert` handles this).
2. Write a down-migration SQL file and apply it manually or via CI:

```typescript
// migrations/0016_revert_add_rate_limit_table.sql
-- Revert migration 0015_add_rate_limit_table
DROP TABLE IF EXISTS rate_limits;
```

```bash
# Apply the down-migration against the production D1 database
npx wrangler d1 execute my-db --env production \
  --file migrations/0016_revert_add_rate_limit_table.sql
```

D1 migrations are one-directional by default — plan reversibility at migration authoring time (see related articles).

---

## GitHub Actions: Revert-Triggered Deploy Pipeline

Ensure the deploy pipeline treats a revert commit identically to a feature commit:

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22

      - run: npm ci

      - name: Run tests (must pass even for reverts)
        run: npm test

      - name: Deploy to production
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Annotate deploy in commit status
        run: |
          DEPLOY_ID=$(npx wrangler deployments list --env production \
            --json 2>/dev/null | jq -r '.[0].id')
          echo "Deployed version: $DEPLOY_ID"
          echo "DEPLOY_ID=$DEPLOY_ID" >> "$GITHUB_STEP_SUMMARY"
```

---

## KV and R2 State After a Revert

`git revert` restores source code, not runtime state. After reverting a Worker that wrote to KV or R2:

- **KV entries written by the bad version remain** — delete them manually or let TTL expire.
- **R2 objects uploaded by the bad version remain** — use `wrangler r2 object delete` or the R2 API to remove them if they are invalid.
- **Durable Objects state is persistent** — a code rollback does not reset Durable Object storage. Plan a migration or reset procedure explicitly.

```typescript
// Emergency KV cleanup after a bad deploy
// Run locally with appropriate API token
import { execSync } from "node:child_process";

const NAMESPACE_ID = "your-kv-namespace-id";
const PREFIX = "rate_limit:";  // prefix written by the bad version

// List and delete all affected keys
const keys: string[] = JSON.parse(
  execSync(
    `npx wrangler kv key list --namespace-id=${NAMESPACE_ID} --prefix="${PREFIX}"`,
    { encoding: "utf8" }
  )
).map((k: { name: string }) => k.name);

for (const key of keys) {
  execSync(
    `npx wrangler kv key delete --namespace-id=${NAMESPACE_ID} "${key}"`,
    { stdio: "inherit" }
  );
}
console.log(`Deleted ${keys.length} KV keys with prefix "${PREFIX}"`);
```

---

## Anti-patterns

- **Using `git reset --hard` on `main`** — rewrites shared history, breaks CI/CD pipelines, and requires a force-push to the protected branch. Always use `git revert` instead.
- **Using `wrangler rollback` as the permanent fix** — the rollback lives only on the Cloudflare side. The next push from `main` will re-deploy the bad code. Always follow a rollback with a `git revert` commit.
- **Reverting without running the test suite** — a revert commit can still fail tests if the reverted code had dependencies on other concurrent changes. Let CI validate the revert before declaring the incident resolved.
- **Not communicating the revert in the incident timeline** — a revert commit on `main` can confuse teammates reviewing git log. Always link the revert commit to the incident issue in the commit body.

---

## Gotchas

- After reverting a commit and later deciding to re-introduce it, `git cherry-pick <original-commit>` will produce an empty commit because the revert is already in history. You must `git revert <revert-commit>` (revert the revert) and then resolve any conflicts with intervening changes.
- `wrangler rollback` targets the deployment version slot, not a git SHA. If multiple deployments happened after the bad one, `wrangler rollback` may roll back more than intended — always specify `--deployment-id`.
- Branch protection rules that require PR reviews also block direct `git push origin main`. In this case, open an emergency PR, use the "emergency bypass" allowlist in branch protection, or pre-approve a bot user for incident reverts.
- `git revert -m 1` reverts the merge commit but does not automatically re-run any side effects from the pre-merge CI — it creates a new commit. The topic branch can be merged again in the future once the issue is fixed.

---

## Verification

```bash
# Confirm revert commit is the inverse of the bad commit
git diff HEAD~1 HEAD   # should be empty or the exact inverse of the bad commit
git diff <bad-commit>~1 <bad-commit>   # original change

# Verify the Worker behaviour is restored after CI deploy
npx wrangler deployments list --env production | head -5

# Check active deployment matches the revert commit
npx wrangler deployments list --env production --json \
  | jq '.[0] | {id, created_on, source}'
```

---

## Related

- `rollback-strategy.md`
- `cherry-pick-revert-bisect.md`
- `github-actions-wrangler-deploy-pipeline.md`
- `workers-d1-migration-ci-pipeline.md`
- `hotfix-process.md`

---

## Sources

- git-revert documentation: https://git-scm.com/docs/git-revert
- Wrangler rollback: https://developers.cloudflare.com/workers/wrangler/commands/#rollback
- Cloudflare D1 migrations: https://developers.cloudflare.com/d1/reference/migrations/
- Cloudflare Durable Objects storage: https://developers.cloudflare.com/durable-objects/api/storage-api/
