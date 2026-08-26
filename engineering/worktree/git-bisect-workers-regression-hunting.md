# Git Bisect Workers Regression Hunting

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Workers endpoint that was healthy three weeks ago now returns 502s or incorrect JSON under specific conditions. The regression was introduced somewhere across 80+ commits and no single PR title gives it away. A bisect-driven hunt narrows it to one commit in minutes rather than hours of log archaeology.

## Context

example project Workers run in Cloudflare's V8 isolate environment, which means runtime errors that pass local Node tests can silently surface only after `wrangler deploy`. The bisect workflow must therefore combine local `wrangler dev --local` smoke tests with a reproducible curl probe so each bisect step can be verified automatically without a full deploy cycle.

## Setting Up a Reproducible Probe

Before bisecting, capture the exact failing request as a shell one-liner and confirm it reproduces the bad behaviour on the current HEAD.

```bash
# probe.sh — run against wrangler dev on port 8787
#!/usr/bin/env bash
set -euo pipefail

response=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -d '{"postId":"abc123"}' \
  http://127.0.0.1:8787/api/posts/react)

if [[ "$response" == "200" ]]; then
  exit 0   # good
else
  echo "Got HTTP $response" >&2
  exit 1   # bad
fi
```

Mark the known-good and known-bad commits before starting:

```bash
git bisect start
git bisect bad HEAD
git bisect good v1.14.0   # last known-good tag
```

## Automating Each Step with wrangler dev

`git bisect run` needs a command that starts the worker, waits for readiness, runs the probe, then tears down. Use a wrapper script so bisect can run unattended.

```bash
#!/usr/bin/env bash
# bisect-runner.sh
set -euo pipefail

# Build and start wrangler dev in background
pnpm run build:worker 2>/dev/null || exit 125  # 125 = skip this commit (build broken)

wrangler dev --local --port 8787 --env staging &
WRANGLER_PID=$!

# Wait for port to open (max 20 s)
for i in $(seq 1 20); do
  if curl -sf http://127.0.0.1:8787/__health > /dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Run probe; capture exit code
bash ./probe.sh
RESULT=$?

kill "$WRANGLER_PID" 2>/dev/null || true
wait "$WRANGLER_PID" 2>/dev/null || true

exit "$RESULT"
```

```bash
git bisect run bash ./bisect-runner.sh
```

Git will automatically checkout commits, run the script, and home in on the first bad commit. With 80 commits, bisect needs at most ⌈log₂(80)⌉ = 7 steps.

## Handling Untestable Commits

Some commits mid-history may have broken builds or missing migrations that make them impossible to test. Use exit code `125` to tell git bisect to skip a commit rather than marking it bad.

```bash
# Inside bisect-runner.sh, replace the build step:
if ! pnpm run build:worker 2>/dev/null; then
  echo "Build failed — skipping commit" >&2
  kill "$WRANGLER_PID" 2>/dev/null || true
  exit 125
fi
```

For D1 schema mismatches between bisect checkouts, apply a baseline migration before the probe:

```bash
# After wrangler dev starts:
wrangler d1 execute example project_DB --local \
  --file=migrations/baseline.sql > /dev/null 2>&1 || true
```

## Inspecting the Culprit Commit

When bisect identifies the bad commit, examine it before resetting:

```bash
# bisect prints something like:
# abc1234 is the first bad commit

git show --stat abc1234
git show abc1234 -- src/handlers/posts.ts
```

Use `git log --oneline abc1234~3..abc1234` to see what changed in the surrounding window. After identifying the regression, reset and create a targeted fix branch:

```bash
git bisect reset
git checkout -b fix/posts-react-502
```

## Anti-patterns

- Running `wrangler deploy` on every bisect step — this burns deploy quota and takes 15–30 s per step; `--local` mode is 10–50× faster.
- Skipping the port-readiness wait loop — the probe races the worker startup and produces false positives.
- Bisecting on a dirty tree — uncommitted changes contaminate the tested checkout. Always stash before `git bisect start`.
- Using `exit 1` instead of `exit 125` for build failures — git marks the commit bad instead of skipping it, shrinking the search range incorrectly.
- Starting bisect without a reproducible probe — if the failure is intermittent, automate a retry loop inside `probe.sh` before running bisect.

## Gotchas

- `wrangler dev --local` does not fully replicate Durable Objects or Queues; if the regression lives in those surfaces, use a staging environment deploy instead of local mode.
- `git bisect run` exits with the exit code of the first bad commit's script, not zero. Check `echo $?` after the run.
- If the good tag predates a `wrangler.toml` change that renames a binding, old checkouts will fail to start. Maintain a `wrangler.bisect.toml` with stable binding names as a workaround.
- Worker code that imports from `@example project/shared` may fail bisect if the shared package version in the monorepo changed between commits. Pin the dependency in `bisect-runner.sh` using `pnpm install --frozen-lockfile` before building.
- Bisect session state lives in `.git/BISECT_*` files. A failed session can be resumed with `git bisect log | git bisect replay -`.

## Verification

After `git bisect reset`, cherry-pick the identified bad commit onto a clean branch, run the probe manually, confirm it returns the bad status code, then revert it and confirm the probe passes. Run the full Workers integration test suite (`pnpm test:integration`) before merging the fix.

## Related

- git-bisect-automated-regression-finding.md
- git-bisect-run-2026.md
- cloudflare-workers-vitest-miniflare-testing.md
- wrangler-environments-staging-production.md
- trunk-based-development-cloudflare-workers.md

## Sources

- https://git-scm.com/docs/git-bisect#_bisect_run
- https://developers.cloudflare.com/workers/wrangler/commands/#dev
- https://developers.cloudflare.com/workers/testing/local-development/
