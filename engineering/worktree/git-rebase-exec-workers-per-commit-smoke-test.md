# Git Rebase --exec: Per-Commit Wrangler Smoke Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A feature branch has 12 commits and a flaky production error that appeared sometime during development—but `git bisect` is overkill because the commit range is small and the test suite takes 90 seconds. `git rebase --exec` runs an arbitrary shell command after each commit as it replays them, stopping the rebase if any command exits non-zero. This lets you run a Wrangler smoke test after every commit in a branch and surface exactly which commit first introduced the failure—without binary search and without leaving the repository in a detached HEAD state mid-investigation.

## Context

`git rebase --exec <cmd>` (also `git rebase -x <cmd>`) injects `exec <cmd>` steps between every `pick` line in the rebase plan. The rebase stops on first failure and leaves the repository at the broken commit so you can inspect it. `git rebase --continue` moves to the next step after you've noted the failure. When combined with Wrangler's `--dry-run` mode or Miniflare, the test harness never touches a real deployment—each step is a local build and health check. The `--exec` flag can also be layered on `--onto` for transplanted branches.

---

## Basic Usage: Smoke-Test Every Commit in a Feature Branch

```bash
#!/usr/bin/env bash
set -euo pipefail

FEATURE_BRANCH=$(git rev-parse --abbrev-ref HEAD)
BASE_BRANCH="main"
BASE_SHA=$(git merge-base HEAD "$BASE_BRANCH")

echo "Replaying commits from $BASE_SHA to HEAD with per-commit smoke tests..."

git rebase "$BASE_SHA" \
  --exec "npm run build:worker && node scripts/smoke-test-local.mjs" \
  --keep-empty
```

If any commit fails, Git stops and reports:

```
error: command failed: npm run build:worker && node scripts/smoke-test-local.mjs
You can fix the problem, and then run

  git rebase --continue

```

## Smoke Test Script: Miniflare Health Check

```typescript
// scripts/smoke-test-local.mjs
// Runs after every commit during git rebase --exec
import { execSync, spawn } from "child_process";

const PORT = 8799; // avoid colliding with dev on 8787
let wranglerProc;

async function startWrangler() {
  return new Promise((resolve, reject) => {
    wranglerProc = spawn(
      "npx",
      ["wrangler", "dev", "--port", String(PORT), "--local"],
      {
        stdio: ["ignore", "pipe", "pipe"],
        detached: false,
      }
    );

    const timeout = setTimeout(() => reject(new Error("Wrangler boot timeout")), 20_000);

    wranglerProc.stdout.on("data", (chunk) => {
      if (chunk.toString().includes("Ready on http")) {
        clearTimeout(timeout);
        resolve(undefined);
      }
    });

    wranglerProc.on("error", reject);
  });
}

async function runChecks() {
  const checks = [
    { path: "/health", expectStatus: 200 },
    { path: "/api/version", expectStatus: 200 },
    { path: "/api/missing", expectStatus: 404 },
  ];

  const commit = execSync("git rev-parse --short HEAD", { encoding: "utf8" }).trim();
  console.log(`\nSmoke tests for commit: ${commit}`);

  for (const { path, expectStatus } of checks) {
    const res = await fetch(`http://localhost:${PORT}${path}`);
    const pass = res.status === expectStatus;
    console.log(`  ${pass ? "✓" : "✗"} GET ${path} → ${res.status} (expected ${expectStatus})`);
    if (!pass) {
      throw new Error(`Check failed: ${path}`);
    }
  }
}

try {
  await startWrangler();
  await runChecks();
  console.log("All checks passed.\n");
} finally {
  wranglerProc?.kill("SIGTERM");
}
```

## Combining --exec with --onto for Environment-Specific Testing

Replay a branch onto a different base (e.g., a release branch) and smoke-test each commit against the target environment's config:

```bash
#!/usr/bin/env bash
# Test that each commit in feature/payments works if we target the v2 base
FEATURE="feature/payments"
RELEASE_BASE="release/v2"

git rebase \
  --onto "$RELEASE_BASE" \
  "$(git merge-base "$FEATURE" main)" \
  "$FEATURE" \
  --exec "WRANGLER_ENV=staging npm run smoke-test"
```

## Selectively Exec Only Commits Touching a Worker

For large branches, skip exec on commits that don't touch Worker source to save time:

```bash
#!/usr/bin/env bash
# Wrapper: only run smoke test if Worker src changed since previous commit
cat > /tmp/conditional-exec.sh << 'EOF'
#!/usr/bin/env bash
CHANGED=$(git diff HEAD~1 HEAD --name-only 2>/dev/null | grep -c "^workers/" || true)
if [[ "$CHANGED" -gt 0 ]]; then
  echo "Worker files changed — running smoke test"
  npm run build:worker && node scripts/smoke-test-local.mjs
else
  echo "No Worker changes in this commit — skipping smoke test"
fi
EOF
chmod +x /tmp/conditional-exec.sh

git rebase "$(git merge-base HEAD main)" \
  --exec "/tmp/conditional-exec.sh"
```

## CI Integration: Per-Commit Validation on PR Branches

Run `rebase --exec` as a CI gate to prevent PRs where an intermediate commit breaks the build (useful for stacked PRs):

```yaml
# .github/workflows/rebase-exec-validation.yml
name: Per-Commit Smoke Test
on:
  pull_request:
    paths:
      - "workers/**"

jobs:
  per-commit-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Replay branch with exec smoke test
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
        run: |
          git config user.email "ci@example.com"
          git config user.name "CI"

          BASE=$(git merge-base HEAD origin/main)
          COMMIT_COUNT=$(git rev-list --count "$BASE"..HEAD)
          echo "Testing $COMMIT_COUNT commits via rebase --exec"

          git rebase "$BASE" \
            --exec "npx wrangler deploy --dry-run --outdir /tmp/deploy-check" \
            --keep-empty

          # If we reach here, all commits built cleanly
          echo "All $COMMIT_COUNT commits passed dry-run deploy check"
```

## Recovering from a Failed Exec

```bash
# The rebase stopped at commit <commit-sha> — inspect the failure
git log --oneline -1   # shows the broken commit

# Check what changed
git show --stat

# Options:
# 1. Fix the commit and continue
#    git add -A && git commit --amend --no-edit
#    git rebase --continue

# 2. Skip this exec step but keep the commit
#    git rebase --skip   # WARNING: skips the commit, not just the exec

# 3. Abort entirely and return to the original branch state
#    git rebase --abort

# To skip ONLY the failing exec and keep the commit:
# Edit the rebase todo file to remove just the 'exec' line for this step
git rebase --edit-todo
# Then: git rebase --continue
```

---

## Anti-patterns

- **Using `--exec` with commands that modify tracked files.** If the exec command writes to tracked files, subsequent commits in the rebase may fail to apply due to dirty working tree. Use `--exec` with read-only validation commands only.
- **Running `--exec` against a real production environment.** Each commit in a 10-commit branch would trigger 10 production deploys. Always use `--local` (Miniflare) or `--dry-run` in `--exec` pipelines.
- **Skipping `git rebase --abort` when debugging.** If you `Ctrl+C` out of a rebase, you leave the repo mid-rebase. Always abort cleanly before switching branches.
- **Using `--exec` as a substitute for CI.** It validates the local developer's environment, not a clean CI environment. Use it as a fast local triage tool; let CI do the authoritative gate.

## Gotchas

- `git rebase --exec` creates a new commit for each `exec` failure notification—it does **not** reset automatically. The working tree stays at the failing commit.
- `HEAD~1` inside the exec command refers to the previously applied commit in the rebase, not the original commit's parent. For reliable diff detection, use `ORIG_HEAD` or compare against a fixed base SHA stored in an environment variable.
- Miniflare's `--local` mode does not support D1 remote databases. If your Worker requires D1, use `wrangler deploy --dry-run` (which validates config and bundle size) instead of a full runtime test.
- Some Wrangler versions print "Ready on http" before all bindings are initialized. Add a brief `sleep 2` before the first HTTP check if you observe intermittent failures on the first check only.

## Verification

```bash
# 1. Create a test branch with a known bad commit
git checkout -b test/rebase-exec-demo main
echo 'export default { fetch() { throw new Error("broken"); } }' \
  > workers/api/src/index.ts
git add . && git commit -m "chore: intentionally broken commit"
echo 'export default { fetch() { return new Response("ok"); } }' \
  > workers/api/src/index.ts
git add . && git commit -m "chore: fixed"

# 2. Run rebase exec — should stop at the broken commit
git rebase "$(git merge-base HEAD main)" \
  --exec "node scripts/smoke-test-local.mjs"
# Expect: stops at first commit, reports failure

# 3. Abort and clean up
git rebase --abort
git checkout main
git branch -D test/rebase-exec-demo
```

## Related

- `git-bisect-workers-regression-hunting.md`
- `git-bisect-automated-regression-finding.md`
- `git-rebase-interactive.md`
- `git-rebase-onto-branch-transplant.md`
- `cloudflare-workers-vitest-miniflare-testing.md`

## Sources

- Git documentation: `git-rebase(1)` — `--exec` flag
- Wrangler `--dry-run` reference: https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- Miniflare local testing: https://miniflare.dev/
- Pro Git Book, Chapter 7: "Rewriting History"
