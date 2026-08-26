# Git Worktree Parallel Feature Branch Testing for Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You are working on two feature branches simultaneously — one adding a new D1 query layer,
another refactoring the routing middleware. Running `wrangler dev` for one branch forces you
to stop and restart for the other. You want both workers live at different ports so you can
run integration tests against each without constantly context-switching.

## Context

`git worktree add` places a second (or third) working tree on disk, each checked out to its
own branch and backed by the same `.git` object store. Because each worktree has its own
`node_modules` symlink target (via pnpm workspaces) and its own `wrangler.jsonc`, you can
bind each `wrangler dev` instance to a distinct local port. Integration tests then target
`http://localhost:<port>` directly, so CI can parallelise across branches with zero port
collision and zero branch-switching overhead.

---

## 1. Provision the Worktrees

```bash
# from the repo root on main
REPO_ROOT=$(pwd)

git worktree add "$REPO_ROOT/../wt-feature-d1"    feature/d1-query-layer
git worktree add "$REPO_ROOT/../wt-feature-router" feature/router-refactor

# install deps in each tree (pnpm hoists to .pnpm-store, symlinks differ per tree)
pnpm --dir "$REPO_ROOT/../wt-feature-d1"    install --frozen-lockfile
pnpm --dir "$REPO_ROOT/../wt-feature-router" install --frozen-lockfile
```

Never share a single `node_modules` across worktrees that differ in lockfile state — each
branch may pin different versions of `wrangler` itself.

## 2. Port-Separated wrangler dev Instances

```jsonc
// wt-feature-d1/wrangler.jsonc
{
  "name": "api-feature-d1",
  "compatibility_date": "2025-11-01",
  "vars": { "BRANCH": "feature/d1-query-layer" },
  "d1_databases": [{ "binding": "DB", "database_name": "api-dev", "database_id": "..." }]
}
```

```bash
# Terminal A — feature/d1-query-layer at port 8788
cd ../wt-feature-d1
pnpm wrangler dev --port 8788 --local --persist-to .wrangler/state

# Terminal B — feature/router-refactor at port 8789
cd ../wt-feature-router
pnpm wrangler dev --port 8789 --local --persist-to .wrangler/state
```

`--persist-to` scopes local KV/D1/R2 state to each worktree directory, preventing cross-
branch state bleed.

## 3. Branch-Aware Integration Test Matrix

```typescript
// tests/integration/branches.config.ts
export interface BranchTarget {
  name: string;
  baseUrl: string;
  worktreePath: string;
}

export const BRANCH_TARGETS: BranchTarget[] = [
  { name: "feature/d1-query-layer",  baseUrl: "http://localhost:8788", worktreePath: "../wt-feature-d1" },
  { name: "feature/router-refactor", baseUrl: "http://localhost:8789", worktreePath: "../wt-feature-router" },
];
```

```typescript
// tests/integration/parallel-runner.ts
import { BRANCH_TARGETS } from "./branches.config";

async function runSuite(target: (typeof BRANCH_TARGETS)[number]) {
  const res = await fetch(`${target.baseUrl}/health`);
  if (!res.ok) throw new Error(`${target.name} health check failed: ${res.status}`);

  const body = await res.json<{ branch: string; ok: boolean }>();
  console.assert(body.ok, `${target.name}: worker not healthy`);
  console.log(`[${target.name}] OK — branch header: ${body.branch}`);
}

await Promise.all(BRANCH_TARGETS.map(runSuite));
```

## 4. CI Matrix Job per Worktree

```yaml
# .github/workflows/feature-branch-test.yml
name: Feature Branch Parallel Tests
on: [pull_request]

jobs:
  test-branches:
    strategy:
      matrix:
        include:
          - branch: feature/d1-query-layer
            port: 8788
          - branch: feature/router-refactor
            port: 8789
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ matrix.branch }}
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile

      - name: Start wrangler dev
        run: pnpm wrangler dev --port ${{ matrix.port }} --local &
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}

      - name: Wait for worker
        run: npx wait-on http://localhost:${{ matrix.port }}/health --timeout 30000

      - name: Run integration tests
        run: pnpm vitest run --reporter=verbose
        env:
          BASE_URL: http://localhost:${{ matrix.port }}
```

## 5. Cleanup Script

```bash
#!/usr/bin/env bash
# scripts/cleanup-feature-worktrees.sh
set -euo pipefail

REPO_ROOT=$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)

for wt_path in "$REPO_ROOT"/../wt-feature-*; do
  [[ -d "$wt_path" ]] || continue
  branch=$(git -C "$wt_path" branch --show-current 2>/dev/null || echo "detached")
  echo "Removing worktree: $wt_path (branch: $branch)"
  git -C "$REPO_ROOT" worktree remove --force "$wt_path"
done

git -C "$REPO_ROOT" worktree prune
echo "Done."
```

---

## Anti-patterns

- **Sharing a single `wrangler dev` process** between branches — port conflicts and wrong
  branch code executing silently.
- **Using `--remote` in `wrangler dev` during branch tests** — preview deployments are not
  per-worktree isolated; local mode is required for true isolation.
- **Omitting `--persist-to`** — local D1/KV state lands in `~/.wrangler/state` shared
  across all worktrees, making test results non-deterministic.
- **Checking out branches with `git checkout` instead of worktrees** — serialises testing
  and discards any running wrangler process.

## Gotchas

- `wrangler dev --local` binds to `127.0.0.1` by default. If your test runner runs inside
  Docker, use `--ip 0.0.0.0` instead.
- Each worktree needs its own `wrangler.jsonc` (or override via `WRANGLER_CONFIG` env var)
  if the two branches differ in bindings — mismatched bindings cause silent 500s, not startup
  failures.
- pnpm hoisting means `node_modules/.pnpm` is shared at the store level but the symlink
  tree in each worktree is independent. Running `pnpm install` in the repo root does **not**
  install in child worktrees.
- If both branches bind to the same D1 `database_id`, local state still isolates via
  `--persist-to`, but remote D1 will be shared. Use separate dev database IDs when testing
  schema migrations.

## Verification

```bash
# Confirm both workers respond and report the correct branch
curl -s http://localhost:8788/health | jq .branch
# => "feature/d1-query-layer"

curl -s http://localhost:8789/health | jq .branch
# => "feature/router-refactor"

# Confirm worktrees are registered
git worktree list
# =>  /repo              abc1234 [main]
# =>  /repo/../wt-feature-d1     def5678 [feature/d1-query-layer]
# =>  /repo/../wt-feature-router ghi9012 [feature/router-refactor]
```

## Related

- `git-worktree-parallel-ci-patterns.md`
- `git-worktree-parallel-wrangler-environments.md`
- `wrangler-environments-staging-production.md`
- `git-worktree-lockfile-isolation.md`
- `cloudflare-workers-vitest-miniflare-testing.md`

## Sources

- Cloudflare Workers `wrangler dev` local mode docs (2025)
- git-worktree(1) man page
- pnpm workspace linking docs — pnpm.io/workspaces
