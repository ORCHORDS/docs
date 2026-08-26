# Using git bisect with Git Worktrees to Hunt Regressions in Workers Deployments

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Workers deployment that was green last week is now returning 500 errors on a specific endpoint, but the responsible commit is buried somewhere in 40+ merges. Manually deploying and testing each commit would take hours. Using `git bisect` inside a dedicated git worktree automates the binary search — each bisect step deploys a candidate commit to a staging environment and runs a regression test script, narrowing the bad commit to a single SHA without affecting the main working tree.

---

## Context

Git bisect performs a binary search over commit history, checking out successive commits and asking whether each one is `good` or `bad`. When driven with `git bisect run`, the process is fully automated: a shell script exits `0` for a good commit and `1` for a bad one. Running bisect inside a separate worktree means the main working directory stays on `main` and can still serve other requests or run other tests. The Wrangler CLI deploys the candidate commit to a staging environment for each bisect step, and a Node.js test script validates whether the regression is present. Once the offending commit is identified, it can be reverted or patched on the main branch.

---

## Section 1 — Create the Bisect Worktree

```bash
# From the repo root on main
git fetch origin --tags

# Create a worktree at HEAD for bisect operations
git worktree add ../bisect-hunt HEAD

git worktree list
# /path/to/project    abc1234 [main]
# /path/to/project  abc1234 (detached HEAD)

cd ../bisect-hunt
npm ci

# Confirm the last known good tag and current bad commit
echo "Good: v2.0.0"
echo "Bad:  $(git rev-parse HEAD)"
```

---

## Section 2 — Scripted Bisect with Wrangler Deploy

```bash
# Create the bisect run script in the bisect worktree
cat > /path/to/project << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

echo "[bisect] Testing commit: $(git rev-parse --short HEAD)"

# Reinstall dependencies for each candidate (handles lock-file changes)
npm ci --silent

# Deploy to staging environment
if ! npx wrangler deploy --env staging --no-bundle=false 2>&1; then
  echo "[bisect] Deploy failed — treating as bad"
  exit 1
fi

# Wait for the deployment to propagate
sleep 5

# Run the regression test
if node /path/to/project then
  echo "[bisect] GOOD"
  exit 0
else
  echo "[bisect] BAD"
  exit 1
fi
EOF
chmod +x /path/to/project
```

```typescript
// test-regression.js — Node.js regression test script
import https from 'https';

const STAGING_URL = process.env.STAGING_URL ?? 'https://my-worker-staging.example.workers.dev';
const TIMEOUT_MS = 10_000;

function get(url: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { timeout: TIMEOUT_MS }, (res) => {
      let body = '';
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => resolve({ status: res.statusCode ?? 0, body }));
    });
    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timed out'));
    });
  });
}

async function main(): Promise<void> {
  const { status, body } = await get(`${STAGING_URL}/api/orders/latest`);
  if (status !== 200) {
    console.error(`FAIL: expected 200, got ${status}`);
    process.exit(1);
  }
  const data = JSON.parse(body) as { orderId: string };
  if (!data.orderId) {
    console.error('FAIL: response missing orderId field');
    process.exit(1);
  }
  console.log(`PASS: orderId=${data.orderId}`);
  process.exit(0);
}

main().catch((err) => {
  console.error('FAIL:', err.message);
  process.exit(1);
});
```

```bash
# Start the bisect session inside the worktree
cd /path/to/project

git bisect start
git bisect bad HEAD            # current HEAD is bad
git bisect good v2.0.0         # last known good tag
# Bisecting: 21 revisions left to test (roughly 5 steps)

# Run the fully automated bisect — each step deploys and tests
git bisect run /path/to/project
# ...
# a3f9c12 is the first bad commit
# commit <commit-sha>
# Author: dev@example.com
# Date:   2026-08-18
#     feat(orders): add pagination to orders endpoint
```

---

## Section 3 — Identify, Revert, and Clean Up

```bash
# Record the offending commit
BAD_COMMIT=$(git bisect log | grep 'first bad commit' | awk '{print $1}' || git rev-parse HEAD)
echo "Offending commit: $BAD_COMMIT"

# End the bisect session
git bisect reset

# Return to main worktree
cd /path/to/project

# Revert the offending commit on main
git revert "$BAD_COMMIT" --no-edit
git push origin main

# Deploy the revert to production
npx wrangler deploy --env production

# Remove the bisect worktree
git worktree remove /path/to/project
git worktree list
```

```bash
# Optionally: open a detailed investigation with git show
git show "$BAD_COMMIT" --stat
git diff "${BAD_COMMIT}~1" "$BAD_COMMIT" -- src/handlers/orders.ts
```

---

## Anti-patterns

- **Running bisect in the main worktree** — `git bisect` checks out successive commits, which will delete unstaged changes and interrupt any running `wrangler dev` session on the main tree.
- **Using a flaky test script** — if `test-regression.js` has network timeouts that randomly return non-zero, bisect will misclassify good commits as bad, producing a wrong answer; add retry logic or increase the timeout.
- **Not calling `npm ci` in the bisect script** — a candidate commit may have different dependencies than the current `node_modules`; skipping reinstall causes false positives when a build fails due to missing packages rather than the actual bug.
- **Forgetting `git bisect reset`** — leaving bisect active puts the worktree in a detached HEAD state; subsequent commands behave unexpectedly until `git bisect reset` is run.

---

## Gotchas

- `git bisect run` exits with the code of the last test run; if the deploy or test script itself errors unexpectedly (network blip, wrangler auth failure), bisect logs it as a bad commit — check the bisect log with `git bisect log` before trusting the result.
- Wrangler staging deploys require a valid `[env.staging]` block in `wrangler.toml`; ensure the staging environment is configured before starting bisect.
- The `test-regression.js` script must target the **staging** URL, not localhost, since each bisect step deploys to the cloud — local `wrangler dev` would not reflect cloud KV or D1 state.
- `git bisect good/bad` commands inside `git bisect run` are determined by exit codes: `0` = good, `1`–`127` (except `125`) = bad, `125` = skip this commit (e.g., it does not compile).
- If a candidate commit does not compile or deploy, exit with `125` in the bisect script to tell git to skip it rather than marking it as bad.

---

## Verification

```bash
# Confirm the revert was pushed and CI is green
git log --oneline origin/main | head -3

# Confirm staging is healthy after the revert deploy
curl -sf https://my-worker-staging.example.workers.dev/api/orders/latest | jq '.orderId'

# Confirm production is healthy
curl -sf https://my-worker.example.workers.dev/api/orders/latest | jq '.orderId'

# Confirm bisect worktree is cleaned up
git worktree list
```

---

## Related

- `git-worktree-hotfix-production-parallel.md`
- `git-worktree-long-running-refactor-isolation.md`

---

## Sources

- Git Bisect Documentation — https://git-scm.com/docs/git-bisect
- Git Worktrees Documentation — https://git-scm.com/docs/git-worktree
- Wrangler Environments — https://developers.cloudflare.com/workers/wrangler/environments/
