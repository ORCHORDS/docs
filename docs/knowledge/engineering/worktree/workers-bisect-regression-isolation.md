# Using git bisect with wrangler to Isolate Performance Regressions

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Cloudflare Workers deployment that was performing within SLA suddenly shows elevated CPU time or
an unexpected jump in compressed bundle size. The regression appeared somewhere across dozens of
commits on the release branch. Manually checking out each commit is too slow. You need an
automated bisect that builds the Worker and measures the metric at each candidate commit.

---

## Context

`git bisect` performs a binary search over the commit history. You mark a known-good commit and a
known-bad commit; git checks out the midpoint; you run a test and report `good` or `bad`; git
halves the remaining range. With `git bisect run`, the entire loop is scripted — no human
intervention is needed after the initial setup.

Wrangler's `wrangler build` subcommand compiles the Worker bundle without deploying it, writing
the output to `.wrangler/dist/`. This makes it suitable for offline metrics:

- **Bundle size regression** — measure the size of the emitted `.js` file.
- **CPU time regression** — use `wrangler dev --local` with a benchmarking HTTP client such as
  `autocannon` and measure median CPU time from Wrangler's structured log output.

---

## Solution

### 1. Start bisect and mark boundaries

```bash
git bisect start
git bisect bad HEAD                    # current commit is bad
git bisect good v2.14.0                # last known-good tag
```

Git will report how many steps remain:

```
Bisecting: 23 revisions left to test after this (roughly 5 steps)
[a3f9c12] refactor: extract auth middleware
```

### 2. Write the automated bisect script

Create `scripts/bisect-bundle-size.sh` (committed to a separate worktree or stashed branch so it
is not affected by the bisected range):

```bash
#!/usr/bin/env bash
set -euo pipefail

THRESHOLD_BYTES=512000   # 500 KB compressed threshold

# Install deps silently; use --frozen-lockfile to catch lockfile drift
npm ci --silent 2>/dev/null || true

# Build the Worker bundle
npx wrangler build 2>/dev/null

# Locate the emitted bundle (adjust glob for your project structure)
BUNDLE=$(find .wrangler/dist -name '*.js' | head -1)

if [ -z "$BUNDLE" ]; then
  echo "[bisect] ERROR: bundle not found" >&2
  exit 125   # 125 tells git bisect to skip this commit
fi

ACTUAL=$(wc -c < "$BUNDLE")
echo "[bisect] bundle size: ${ACTUAL} bytes (threshold: ${THRESHOLD_BYTES})"

if [ "$ACTUAL" -gt "$THRESHOLD_BYTES" ]; then
  exit 1   # bad
else
  exit 0   # good
fi
```

Make it executable:

```bash
chmod +x scripts/bisect-bundle-size.sh
```

### 3. Run automated bisect

```bash
git bisect run ./scripts/bisect-bundle-size.sh
```

Git will iterate through candidate commits automatically, printing:

```
[bisect] bundle size: 489231 bytes (threshold: 512000)   -> good
[bisect] bundle size: 538902 bytes (threshold: 512000)   -> bad
...
abc1234deadbeef is the first bad commit
commit <commit-sha>
Author: Dev Name <dev@example.com>
Date:   Mon Aug 12 14:22:03 2024

    feat: add polyfill for TextEncoder in legacy environments
```

### 4. CPU time bisect variant

For CPU time regressions, use `wrangler dev --local` and drive it with a benchmark client.
This requires a slightly longer script:

```bash
#!/usr/bin/env bash
set -euo pipefail

CPU_THRESHOLD_MS=50
BENCH_REQUESTS=200
PORT=19999   # dedicated bisect port to avoid collisions

npm ci --silent 2>/dev/null || true

# Start wrangler dev in background
npx wrangler dev --port "$PORT" --local &
WRANGLER_PID=$!
trap 'kill $WRANGLER_PID 2>/dev/null || true' EXIT

# Wait for the dev server to become ready
for i in $(seq 1 30); do
  if curl -sf "http://localhost:${PORT}/" > /dev/null 2>&1; then break; fi
  sleep 0.5
done

# Benchmark with autocannon
RESULT=$(npx autocannon \
  --connections 1 \
  --duration 5 \
  --json \
  "http://localhost:${PORT}/bench")

MEDIAN=$(echo "$RESULT" | node -e \
  "process.stdin.resume(); let d=''; process.stdin.on('data',c=>d+=c);
   process.stdin.on('end',()=>console.log(JSON.parse(d).latency.p50));")

echo "[bisect] p50 latency: ${MEDIAN}ms (threshold: ${CPU_THRESHOLD_MS}ms)"

[ "$MEDIAN" -le "$CPU_THRESHOLD_MS" ] && exit 0 || exit 1
```

### 5. TypeScript bisect runner for CI

```typescript
// scripts/bisect-runner.ts
import { execSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';

const THRESHOLD_BYTES = 512_000;

function buildWorker(): void {
  execSync('npm ci --silent', { stdio: 'ignore' });
  execSync('npx wrangler build', { stdio: 'pipe' });
}

function measureBundleSize(): number {
  const dist = '.wrangler/dist';
  const files = fs.readdirSync(dist).filter((f) => f.endsWith('.js'));
  if (!files.length) throw new Error('No bundle found in ' + dist);
  const stats = fs.statSync(`${dist}/${files[0]}`);
  return stats.size;
}

function main(): void {
  try {
    buildWorker();
  } catch {
    // Build failure — skip this commit
    process.exit(125);
  }

  const size = measureBundleSize();
  console.log(`[bisect] bundle: ${size} bytes`);
  process.exit(size > THRESHOLD_BYTES ? 1 : 0);
}

main();
```

Invoke via:

```bash
git bisect run npx ts-node scripts/bisect-runner.ts
```

---

## Implementation Details

### Skipping commits that do not build

Exit code `125` instructs `git bisect` to skip the current commit rather than marking it good or
bad. Use this for commits where `npm ci` or `wrangler build` fails due to unrelated breakage.

### Annotating the bad commit

Once bisect identifies the first bad commit, annotate it:

```bash
# Record the findings in a git note
git notes add -m "bundle-regression: size exceeded 512KB threshold" abc1234
git notes push origin refs/notes/commits
```

Or open a GitHub issue programmatically in your bisect script:

```bash
BAD_SHA=$(git bisect log | grep 'first bad' | awk '{print $4}')
gh issue create \
  --title "Bundle regression introduced at ${BAD_SHA:0:8}" \
  --body "Bisect result: commit ${BAD_SHA} caused bundle to exceed 512 KB threshold."
```

### Bisecting on bundle size across multiple entry points

```bash
TOTAL=0
for bundle in .wrangler/dist/*.js; do
  SIZE=$(wc -c < "$bundle")
  TOTAL=$((TOTAL + SIZE))
done
echo "[bisect] total: ${TOTAL} bytes"
[ "$TOTAL" -le "$THRESHOLD_BYTES" ] && exit 0 || exit 1
```

---

## Anti-patterns

- **Using `wrangler deploy` as the bisect probe.** This performs a real deployment on each
  bisect step, consuming rate limit and potentially breaking a live environment.
- **Not pinning node/npm versions in the bisect script.** If the commit range spans a tooling
  upgrade, `npm ci` may behave differently at different commits. Use `.nvmrc` or `nvm use` in
  the script.
- **Ignoring exit code 125.** If your script always exits 0 or 1, git bisect will mark broken
  builds as good or bad rather than skipping them, producing a wrong result.

---

## Gotchas

- `git bisect run` resets the working tree before each step, discarding any uncommitted changes.
  Keep your bisect script on a branch or absolute path outside the worktree being bisected.
- `wrangler build` does not emit source maps by default in all versions. If your size threshold
  includes source maps, set `WRANGLER_BUILD_SOURCEMAP=1` explicitly.
- Bisect log is preserved in `.git/BISECT_LOG` until you run `git bisect reset`. Save it
  before resetting if you want a permanent record.

---

## Verification

```bash
# After bisect identifies the bad commit, verify manually
git checkout abc1234
npx wrangler build
wc -c .wrangler/dist/*.js

# Then reset bisect state
git bisect reset
```

---

## Related

- `workers-worktree-parallel-wrangler-dev.md` — isolating feature branches in separate trees
- `workers-gitops-auto-deploy-main-branch.md` — automated deployment and rollback
- `workers-monorepo-selective-deploy-changeset.md` — per-package change detection

---

## Sources

- https://git-scm.com/docs/git-bisect
- https://developers.cloudflare.com/workers/wrangler/commands/#build
- https://developers.cloudflare.com/workers/observability/metrics/
