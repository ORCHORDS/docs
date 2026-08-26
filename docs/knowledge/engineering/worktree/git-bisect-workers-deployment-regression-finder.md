# Git Bisect for Cloudflare Workers Deployment Regression Hunting

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker that was healthy last week now returns 5xx errors or exhibits a 200 ms latency regression in production. You know the range of suspect commits but there are dozens of them and reading each diff manually is impractical. You need to binary-search the commit history to pinpoint the exact commit that introduced the regression.

## Context

Git bisect performs a binary search between a known-good and known-bad commit by checking out the midpoint, letting you test it, and narrowing the range based on your verdict. The automated mode (`git bisect run`) replaces manual verdicts with a script's exit code (0 = good, 1–127 = bad, 125 = skip). For Cloudflare Workers this means deploying the bisect candidate with `wrangler deploy`, running a smoke test or latency check against the deployed URL, and returning the appropriate exit code. The Cloudflare Versions API lets you correlate deployed Worker versions with git SHAs without performing a full deploy for every candidate.

## Writing the Bisect Script

Create a script that deploys and tests the current checkout:

```bash
#!/usr/bin/env bash
# scripts/test-deploy.sh
set -euo pipefail

WORKER_NAME="${WORKER_NAME:-api-gateway}"
ENV="${CF_ENV:-staging}"
SMOKE_URL="${SMOKE_URL:-https://api-staging.example.com/healthz}"
LATENCY_THRESHOLD_MS="${LATENCY_THRESHOLD_MS:-300}"

# Exit 125 = skip this commit (bisect will move to the next one)
skip_if_unbuildable() {
  echo "[bisect] build failed — skipping commit $(git rev-parse --short HEAD)"
  exit 125
}

echo "[bisect] Testing commit: $(git rev-parse --short HEAD)"
echo "[bisect] Message: $(git log -1 --pretty=%s)"

# Install deps (use cached node_modules when possible)
pnpm install --frozen-lockfile --prefer-offline 2>/dev/null \
  || skip_if_unbuildable

# Build
pnpm --filter "$WORKER_NAME" run build 2>/dev/null \
  || skip_if_unbuildable

# Deploy to staging
pnpm --filter "$WORKER_NAME" exec wrangler deploy \
  --env "$ENV" \
  --name "${WORKER_NAME}-bisect" 2>/dev/null \
  || skip_if_unbuildable

# Wait for deployment to propagate
sleep 5

# Smoke test: check HTTP status
HTTP_STATUS=$(curl -o /dev/null -s -w '%{http_code}' "$SMOKE_URL")
if [ "$HTTP_STATUS" -ge 500 ]; then
  echo "[bisect] BAD — HTTP $HTTP_STATUS from $SMOKE_URL"
  exit 1
fi

# Latency test: measure p50 over 5 requests
TOTAL_MS=0
for i in $(seq 1 5); do
  MS=$(curl -o /dev/null -s -w '%{time_total}' "$SMOKE_URL" \
       | awk '{printf "%d", $1 * 1000}')
  TOTAL_MS=$((TOTAL_MS + MS))
done
P50_MS=$((TOTAL_MS / 5))

if [ "$P50_MS" -gt "$LATENCY_THRESHOLD_MS" ]; then
  echo "[bisect] BAD — p50 latency ${P50_MS}ms > threshold ${LATENCY_THRESHOLD_MS}ms"
  exit 1
fi

echo "[bisect] GOOD — HTTP $HTTP_STATUS, p50 ${P50_MS}ms"
exit 0
```

Make the script executable:

```bash
chmod +x scripts/test-deploy.sh
```

## Running the Automated Bisect

```bash
# Start bisect, marking known boundaries
git bisect start
git bisect bad HEAD                          # current HEAD is bad
git bisect good v2.14.0                      # last known-good tag

# Hand control to the script — git checks out midpoints automatically
export WORKER_NAME=api-gateway
export CF_ENV=staging
export SMOKE_URL=https://api-staging.example.com/healthz
export CLOUDFLARE_API_TOKEN=<your-token>
export CLOUDFLARE_ACCOUNT_ID=<your-account-id>

git bisect run ./scripts/test-deploy.sh

# Git prints the first bad commit when bisect completes:
# a3f8c21 is the first bad commit
# commit <commit-sha>...
# Author: ...
```

## Using the Cloudflare Versions API to Correlate SHAs

If deploying every bisect candidate is too slow, you can correlate already-deployed versions with git SHAs using Cloudflare's Versions API and bisect against that metadata:

```bash
# List recent Worker versions with their metadata
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$WORKER_NAME/versions" \
  -H "Authorization: Bearer $CF_API_TOKEN" | \
  jq '.result[] | {version_id: .id, deployed_at: .metadata.created_on, message: .metadata.message}'

# If you inject git SHA into the Worker build via an env var:
# In wrangler.toml:
# [vars]
# GIT_SHA = "" # overridden at build time
#
# In CI:
# wrangler deploy --var GIT_SHA:$(git rev-parse HEAD)
#
# Then correlate:
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$WORKER_NAME/versions" \
  -H "Authorization: Bearer $CF_API_TOKEN" | \
  jq '.result[] | {version_id: .id, git_sha: .resources.script.etag}'
```

With SHAs available from Versions API metadata, write a lighter bisect script that only calls the API rather than redeploying:

```bash
#!/usr/bin/env bash
# scripts/bisect-via-api.sh — no deploy, checks latency of an already-live version
SHA=$(git rev-parse HEAD)
VERSION_ID=$(curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/$WORKER_NAME/versions" \
  -H "Authorization: Bearer $CF_API_TOKEN" | \
  jq -r ".result[] | select(.metadata.message | contains(\"$SHA\")) | .id" | head -1)

if [ -z "$VERSION_ID" ]; then
  echo "[bisect] No deployed version for SHA $SHA — skipping"
  exit 125
fi
# ... run latency test against version-pinned URL
```

## Latency Regression Strategy

For latency regressions (not hard failures), adapt the exit threshold dynamically:

```bash
# Measure baseline latency from the known-good commit first
git stash
git checkout "$GOOD_SHA"
BASELINE_MS=$(curl -o /dev/null -s -w '%{time_total}' "$SMOKE_URL" | awk '{printf "%d", $1 * 1000}')
git checkout -
git stash pop

# Set threshold to 1.5× baseline
export LATENCY_THRESHOLD_MS=$(echo "$BASELINE_MS * 1.5 / 1" | bc)
echo "Baseline: ${BASELINE_MS}ms  Threshold: ${LATENCY_THRESHOLD_MS}ms"

git bisect run ./scripts/test-deploy.sh
```

## Safely Resetting After Bisect

```bash
# Always reset bisect when done — returns HEAD to its pre-bisect position
git bisect reset

# Confirm HEAD is restored
git log --oneline -3

# Remove the bisect-specific staging Worker
wrangler delete --name api-gateway-bisect --env staging || true

# View bisect log for audit trail
git bisect log

# Save bisect log for postmortem
git bisect log > postmortems/bisect-$(date +%Y%m%d-%H%M%S).log
```

## Anti-patterns

- **Not calling `git bisect reset` after the session** — leaves HEAD detached at the bad commit; subsequent `git pull` and branch operations behave unexpectedly.
- **Deploying to production during bisect** — use a dedicated staging environment or a uniquely-named Worker (`--name <name>-bisect`) to avoid exposing unstable code to real traffic.
- **Using `exit 1` for build failures instead of `exit 125`** — exit code 1 marks the candidate as bad; build failures due to missing deps or unrelated issues should be skipped with 125.
- **Not injecting the git SHA into the Worker at build time** — without a SHA in the Worker metadata, correlating deployed versions to commits requires manual log review.
- **Bisecting across a merge commit that changes `package.json` drastically** — `pnpm install` may fail or take 10+ minutes on old lockfile states; mark those commits as skip.

## Gotchas

- `git bisect run` requires the script to be executable and located in a path that does not change between commits; keep bisect scripts outside `src/` in a top-level `scripts/` directory.
- Cloudflare propagates a new Worker version to all edge nodes in ~30 seconds; the `sleep 5` in the script may be insufficient for cold-start latency tests — increase to 30s for latency-sensitive bisects.
- The `--name` override in `wrangler deploy --name <name>-bisect` must also match `wrangler.toml` bindings if the Worker references itself or has service bindings.
- `git bisect` requires at least one good and one bad commit; if the good tag predates the repository history in a submodule, use a commit SHA instead.
- `git bisect log` output is human-readable but not machine-parseable; pipe through `grep '^git bisect'` to extract just the commands for replay.

## Verification

```bash
# Dry-run bisect without deploying — verify the commit range
git bisect start
git bisect bad HEAD
git bisect good v2.14.0
git bisect visualize --oneline    # shows commits in range
git bisect reset

# Test the bisect script manually on the current HEAD
./scripts/test-deploy.sh; echo "Exit: $?"

# Verify the cleanup Worker was removed
wrangler list | grep bisect || echo 'clean'

# Count commits in bisect range (log(n) steps needed)
git rev-list v2.14.0..HEAD --count
# 48 commits → 6 steps
```

## Related

- `git-worktree-ci-matrix-parallel-workers-deploy.md`
- `renovate-automerge-cloudflare-workers-deps.md`

## Sources

- git bisect documentation — https://git-scm.com/docs/git-bisect
- Cloudflare Workers Versions API — https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/
- Wrangler deploy reference — https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- Cloudflare edge propagation times — https://developers.cloudflare.com/workers/observability/logs/workers-logs/
