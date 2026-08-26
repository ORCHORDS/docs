# Running CI Test Suites in Parallel Worktrees on One Machine

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A large test suite is slow when run sequentially. On a machine with multiple CPU cores (local developer box or a fat CI runner), you can shard the suite across parallel `git worktree` checkouts. Each shard has its own working directory and dependency install, they all share the same Git object store, and `xargs -P` (or GNU parallel) fans them out with a single command. This article covers the full setup: worktree creation per shard, parallel execution, result collection, and cleanup.

## Context

- Git 2.15+
- Node.js project with Jest or Vitest (patterns apply to Go, Python pytest, etc.)
- Linux/macOS CI runner with 4–16 cores
- Shell: bash

---

## Section 1: Creating One Worktree Per Test Shard

```bash
#!/usr/bin/env bash
# scripts/ci-worktree-setup.sh
# Creates N worktrees for parallel test sharding
# Usage: bash ci-worktree-setup.sh <num-shards> <branch>
# Example: bash ci-worktree-setup.sh 4 main

set -euo pipefail

NUM_SHARDS="${1:-4}"
BRANCH="${2:-main}"
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$REPO_ROOT")
PARENT=$(dirname "$REPO_ROOT")
WT_BASE="${PARENT}/${REPO_NAME}--shard"

git fetch origin "$BRANCH"

for i in $(seq 1 "$NUM_SHARDS"); do
  WT_PATH="${WT_BASE}-${i}"
  if [ -d "$WT_PATH" ]; then
    echo "[shard $i] Worktree already exists at $WT_PATH — skipping add"
  else
    git worktree add "$WT_PATH" "origin/$BRANCH"
    echo "[shard $i] Created worktree at $WT_PATH"
  fi
done

echo "Worktrees ready:"
git worktree list
```

---

## Section 2: Installing Dependencies in Parallel

```bash
#!/usr/bin/env bash
# scripts/ci-install-deps.sh
# Runs npm ci in all shard worktrees in parallel

set -euo pipefail

NUM_SHARDS="${1:-4}"
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$REPO_ROOT")
PARENT=$(dirname "$REPO_ROOT")
WT_BASE="${PARENT}/${REPO_NAME}--shard"

install_shard() {
  local i="$1"
  local wt="${WT_BASE}-${i}"
  echo "[shard $i] npm ci starting..."
  npm ci --prefix "$wt" --silent
  echo "[shard $i] npm ci done"
}

export -f install_shard
export WT_BASE

# xargs -P runs N processes in parallel
seq 1 "$NUM_SHARDS" | xargs -P "$NUM_SHARDS" -I{} bash -c 'install_shard "$@"' _ {}

echo "All shards: deps installed"
```

---

## Section 3: Running Jest Shards in Parallel with `xargs -P`

```bash
#!/usr/bin/env bash
# scripts/ci-run-shards.sh
# Runs Jest with --shard=I/N in each worktree

set -euo pipefail

NUM_SHARDS="${1:-4}"
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$REPO_ROOT")
PARENT=$(dirname "$REPO_ROOT")
WT_BASE="${PARENT}/${REPO_NAME}--shard"
RESULTS_DIR="/tmp/ci-shard-results"
mkdir -p "$RESULTS_DIR"

run_shard() {
  local i="$1"
  local total="$2"
  local wt="${WT_BASE}-${i}"
  local log="${RESULTS_DIR}/shard-${i}.log"
  local exit_code_file="${RESULTS_DIR}/shard-${i}.exit"

  echo "[shard $i/$total] Starting Jest shard ${i}/${total}..."
  (
    cd "$wt"
    npx jest \
      --shard="${i}/${total}" \
      --ci \
      --forceExit \
      --reporters=default \
      --reporters=jest-junit \
      --outputFile="${RESULTS_DIR}/junit-shard-${i}.xml" \
      2>&1
  ) > "$log" 2>&1
  echo $? > "$exit_code_file"
  echo "[shard $i/$total] Done — exit $(cat $exit_code_file)"
}

export -f run_shard
export WT_BASE RESULTS_DIR

# Fan out in parallel
seq 1 "$NUM_SHARDS" | xargs -P "$NUM_SHARDS" -I{} bash -c 'run_shard {} "$NUM_SHARDS"' _ {}

# Collect results
FAILED=0
for i in $(seq 1 "$NUM_SHARDS"); do
  CODE=$(cat "${RESULTS_DIR}/shard-${i}.exit" 2>/dev/null || echo 1)
  if [ "$CODE" -ne 0 ]; then
    echo "FAIL: shard $i"
    cat "${RESULTS_DIR}/shard-${i}.log"
    FAILED=$((FAILED + 1))
  else
    echo "PASS: shard $i"
  fi
done

[ "$FAILED" -eq 0 ] && echo "All shards passed" || { echo "$FAILED shard(s) failed"; exit 1; }
```

---

## Section 4: GitHub Actions Workflow Integration

```yaml
# .github/workflows/parallel-tests.yml
name: Parallel Tests (Worktree Shards)

on:
  push:
    branches: [main, 'release/**']
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    # ubuntu-latest: 2 cores; use self-hosted for more
    env:
      NUM_SHARDS: 4

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history needed for worktree add

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Create shard worktrees
        run: bash scripts/ci-worktree-setup.sh $NUM_SHARDS ${{ github.sha }}
        # Note: use SHA not branch — branch may be locked by the current checkout

      - name: Install deps in all shards
        run: bash scripts/ci-install-deps.sh $NUM_SHARDS

      - name: Run test shards in parallel
        run: bash scripts/ci-run-shards.sh $NUM_SHARDS

      - name: Upload JUnit reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-results
          path: /tmp/ci-shard-results/junit-shard-*.xml

      - name: Cleanup worktrees
        if: always()
        run: |
          bash scripts/ci-worktree-teardown.sh $NUM_SHARDS
```

---

## Section 5: Cleanup Script

```bash
#!/usr/bin/env bash
# scripts/ci-worktree-teardown.sh
# Removes all shard worktrees and prunes refs

set -euo pipefail

NUM_SHARDS="${1:-4}"
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$REPO_ROOT")
PARENT=$(dirname "$REPO_ROOT")
WT_BASE="${PARENT}/${REPO_NAME}--shard"

for i in $(seq 1 "$NUM_SHARDS"); do
  WT_PATH="${WT_BASE}-${i}"
  if [ -d "$WT_PATH" ]; then
    git worktree remove --force "$WT_PATH"
    echo "[shard $i] Removed $WT_PATH"
  else
    echo "[shard $i] $WT_PATH not found — skipping"
  fi
done

git worktree prune --verbose
echo "Cleanup complete"
git worktree list
```

---

## Section 6: TypeScript Shard Orchestrator

```typescript
#!/usr/bin/env ts-node
// scripts/shard-orchestrator.ts
// Programmatic alternative to the bash scripts above

import { execSync, spawn } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

const NUM_SHARDS = parseInt(process.env.NUM_SHARDS ?? '4', 10);
const BRANCH = process.env.BRANCH ?? 'main';

const repoRoot = execSync('git rev-parse --show-toplevel').toString().trim();
const repoName = path.basename(repoRoot);
const parentDir = path.dirname(repoRoot);
const wtBase = `${parentDir}/${repoName}--shard`;
const resultsDir = '/tmp/ci-shard-results';

fs.mkdirSync(resultsDir, { recursive: true });

const run = (cmd: string, cwd = repoRoot) =>
  execSync(cmd, { cwd, stdio: 'inherit' });

// 1. Create worktrees
run(`git fetch origin ${BRANCH}`);
for (let i = 1; i <= NUM_SHARDS; i++) {
  const wt = `${wtBase}-${i}`;
  if (!fs.existsSync(wt)) {
    run(`git worktree add "${wt}" origin/${BRANCH}`);
  }
  run('npm ci --silent', wt);
}

// 2. Spawn parallel Jest processes
const procs = Array.from({ length: NUM_SHARDS }, (_, idx) => {
  const shard = idx + 1;
  const wt = `${wtBase}-${shard}`;
  const logFile = fs.createWriteStream(`${resultsDir}/shard-${shard}.log`);

  return new Promise<{ shard: number; code: number }>((resolve) => {
    const child = spawn(
      'npx',
      ['jest', `--shard=${shard}/${NUM_SHARDS}`, '--ci', '--forceExit'],
      { cwd: wt, stdio: ['ignore', logFile, logFile] }
    );
    child.on('close', (code) => resolve({ shard, code: code ?? 1 }));
  });
});

const results = await Promise.all(procs);

// 3. Report
let failed = 0;
for (const { shard, code } of results) {
  if (code !== 0) {
    console.error(`FAIL: shard ${shard}`);
    console.error(fs.readFileSync(`${resultsDir}/shard-${shard}.log`, 'utf8'));
    failed++;
  } else {
    console.log(`PASS: shard ${shard}`);
  }
}

// 4. Cleanup
for (let i = 1; i <= NUM_SHARDS; i++) {
  run(`git worktree remove --force "${wtBase}-${i}"`);
}
run('git worktree prune');

process.exit(failed > 0 ? 1 : 0);
```

---

## Anti-patterns

- Do not place shard worktrees inside `$REPO_ROOT` — Git will see them as untracked directories.
- Do not share a single `node_modules` across shards — concurrent `npm ci` runs will race on file writes. Each shard must have its own installation.
- Do not use `xargs -P` with more processes than available CPU cores — thrashing defeats the purpose.
- Do not skip `git fetch --depth=0` (full fetch) on shallow clones when using `git worktree add` — shallow clones may lack the commit the worktree branch points to.

## Gotchas

- **Disk space**: 4 shards × 200 MB `node_modules` = 800 MB. Cache `node_modules` in CI or use `npm ci` with the `--cache` flag pointing to a shared cache dir.
- **Port conflicts**: if tests start servers, each shard must bind to a different port. Use `TEST_PORT=$((3000 + SHARD_INDEX))` and configure your test framework accordingly.
- **Jest `--shard` requires Jest 29+**: earlier versions don't support the flag. Use manual `--testPathPattern` sharding for older versions.
- **Worktrees and `git stash`**: stash is global to the repo. Stashing in one worktree is visible in all others via `git stash list`.

## Verification

```bash
# Confirm all shards are distinct worktrees
git worktree list --porcelain | grep ^worktree

# Confirm all shards ran (check log timestamps)
ls -la /tmp/ci-shard-results/

# Dry-run shard 1 to confirm Jest sharding works
pushd "$(git rev-parse --show-toplevel | xargs dirname)/$(basename $(git rev-parse --show-toplevel))--shard-1"
npx jest --shard=1/4 --listTests 2>/dev/null | head -10
popd
```

## Related

- `documentation/categories/worktree/git-worktree-prune-cleanup-automation.md`
- `documentation/categories/worktree/git-worktree-code-review-parallel-checkout.md`
- `documentation/categories/worktree/git-worktree-stash-vs-worktree-comparison.md`

## Sources

- https://git-scm.com/docs/git-worktree
- https://jestjs.io/docs/configuration#shard-string
- https://www.gnu.org/software/coreutils/manual/html_node/xargs-invocation.html
- https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions
