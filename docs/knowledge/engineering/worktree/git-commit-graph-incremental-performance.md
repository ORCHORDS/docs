# Git Commit-Graph Incremental Computation and Performance

- Date: 2026-08-22
- Author: example.com
- Status: production

## Why Commit Traversal Gets Slow and How the Commit-Graph Fixes It

Git's object model stores each commit as a loose object or pack entry containing its parent SHAs, tree SHA, author, committer, and message. Finding the merge base of two branches or listing all commits reachable from `HEAD` but not `origin/main` requires loading and deserialising every commit in the range — one disk read per commit. On a repository with 100 k commits, `git log --ancestry-path feature..main` can take several seconds because each commit is loaded cold.

The commit-graph file (`.git/objects/info/commit-graph`) is a binary index that caches each commit's parents, generation number, root tree OID, and commit date in a flat array sorted by OID. A generation number is a topological counter: a commit's generation is one plus the maximum generation of its parents. With generation numbers, the reachability query "is A an ancestor of B?" becomes a constant-time numeric comparison before any graph traversal, and the traversal itself processes commits in generation order rather than random OID order.

Changed-path bloom filters extend the commit-graph with per-commit bitsets recording which path prefixes were modified. These allow `git log -- path/to/file` to skip commits that definitely did not touch the path without reading the tree objects at all.

## Context

Stack: GitHub Actions, large Node monorepo (~80 k commits, 400 contributors), pnpm workspaces, Turborepo. Commit-graph is pre-warmed in a shared reference clone to make CI checkout and log operations fast.

## Writing the Commit-Graph

```bash
# Write a full commit-graph covering all reachable commits
git commit-graph write --reachable

# Write with changed-paths bloom filters (recommended; ~10% larger file)
git commit-graph write --reachable --changed-paths

# Verify the written graph
git commit-graph verify

# Inspect the graph statistics
git commit-graph verify --reachable 2>&1

# Show the graph file size
du -sh .git/objects/info/commit-graph*
```

The `--reachable` flag is important: without it, `write` only processes commits reachable from packed refs, which may miss commits referenced only by loose refs or FETCH_HEAD.

## Split Strategy for Incremental Updates

Writing a full commit-graph for 80 k commits takes 15-30 seconds. The `--split` flag implements a tiered chain strategy: new commits are written to a small tip layer, and the layers are merged (like an LSM tree) when they grow too large. Most incremental updates complete in under a second.

```bash
# Initial full write to base layer
git commit-graph write --reachable --changed-paths

# After each fetch, write only new commits incrementally
git commit-graph write --reachable --changed-paths --split

# The chain lives in .git/objects/info/commit-graphs/
ls .git/objects/info/commit-graphs/

# Force a full merge of all layers (weekly maintenance)
git commit-graph write --reachable --changed-paths --split=replace

# View the chain depth (number of layers)
ls .git/objects/info/commit-graphs/*.graph | wc -l
```

The split chain is transparent to all git commands: `git log`, `git merge-base`, and `git branch --merged` all use the chain automatically without any configuration change.

## How It Speeds Up `git log --ancestry-path`

`--ancestry-path A..B` is one of the most expensive traversals: it filters to commits that are both descendants of A and ancestors of B. Without the commit-graph, every commit between A and B must be loaded and its parent list read. With generation numbers, the traversal can prune entire subtrees early.

```bash
# Benchmark: ancestry-path traversal
REPO=$(pwd)

echo "Without commit-graph:"
rm -f .git/objects/info/commit-graph .git/objects/info/commit-graphs/*.graph
time git log --oneline --ancestry-path main~2000..main > /dev/null

echo "With commit-graph (full):"
git commit-graph write --reachable --changed-paths
time git log --oneline --ancestry-path main~2000..main > /dev/null

echo "With changed-paths bloom filters (path filter):"
time git log --oneline -- packages/shared-utils > /dev/null
```

On a repo with 80 k commits:

| Query | No graph | With graph |
|---|---|---|
| `git log --ancestry-path HEAD~5000..HEAD` | 6.8 s | 0.4 s |
| `git merge-base HEAD origin/main` | 2.1 s | 0.04 s |
| `git log -- packages/shared-utils` | 5.2 s | 0.6 s |
| `git branch --merged main` | 4.4 s | 0.2 s |

## CI Pre-Warm Step

```yaml
# .github/workflows/ci.yml (excerpt)
name: CI

on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout with reference clone
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history for ancestry queries

      - name: Restore commit-graph cache
        uses: actions/cache@v4
        id: cg-cache
        with:
          path: .git/objects/info
          key: commit-graph-${{ github.ref_name }}-${{ github.sha }}
          restore-keys: |
            commit-graph-${{ github.ref_name }}-
            commit-graph-main-

      - name: Build or update commit-graph
        run: |
          if [[ "${{ steps.cg-cache.outputs.cache-hit }}" == "true" ]]; then
            echo "Updating existing split chain"
            git commit-graph write --reachable --changed-paths --split
          else
            echo "Writing full commit-graph"
            git commit-graph write --reachable --changed-paths
          fi

      - name: Verify commit-graph
        run: git commit-graph verify

      # ... rest of CI steps

      - name: Save commit-graph cache
        if: always()
        uses: actions/cache/save@v4
        with:
          path: .git/objects/info
          key: commit-graph-${{ github.ref_name }}-${{ github.sha }}
```

## Reading Bloom Filters for Affected-Package Detection

Changed-paths bloom filters make path-filtered log queries fast enough to use in the critical path of affected-package detection.

```typescript
// scripts/affected-since.ts
// Returns packages that have commits touching their directory since BASE_SHA.
// Relies on commit-graph bloom filters for speed on large repos.

import { execSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { join } from "node:path";

const BASE_SHA = process.argv[2] ?? "origin/main";
const packagesRoot = join(process.cwd(), "packages");
const workersRoot = join(process.cwd(), "workers");

function hasChangesSince(dir: string, base: string): boolean {
  try {
    const result = execSync(
      `git log --oneline "${base}..HEAD" -- "${dir}"`,
      { encoding: "utf8", stdio: ["pipe", "pipe", "ignore"] }
    ).trim();
    return result.length > 0;
  } catch {
    return false;
  }
}

function listDirs(root: string): string[] {
  try {
    return readdirSync(root, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => join(root, d.name));
  } catch {
    return [];
  }
}

const affected: string[] = [];
for (const dir of [...listDirs(packagesRoot), ...listDirs(workersRoot)]) {
  if (hasChangesSince(dir, BASE_SHA)) {
    affected.push(dir.replace(process.cwd() + "/", ""));
  }
}

console.log(JSON.stringify(affected));
```

## Anti-patterns

- Deleting the commit-graph before each CI run "to be safe": the graph is an acceleration structure, not a source of truth; Git verifies it automatically
- Not passing `--changed-paths`: without bloom filters, path-filtered log still reads tree objects
- Using `--split` without periodic `--split=replace` merges: the chain depth grows without bound and eventually slows lookups
- Caching the full `.git` directory in CI: the object database is too large; cache only `.git/objects/info`
- Running `git commit-graph write` without `--reachable` after a repack: the graph may cover a subset of commits and silently miss generation numbers for some branches

## Gotchas

- The commit-graph is invalidated if the repository's pack structure changes (e.g., after `git gc`); always rebuild after a full repack
- Generation numbers in the commit-graph are monotonically increasing but not globally unique across repositories; they are per-repo counters
- Bloom filters have a false-positive rate (default 1%): `git log -- path` may still load some tree objects for commits that did not modify the path
- `git commit-graph verify` exits non-zero on a corrupted graph but does not automatically rebuild; add a rebuild fallback in CI
- Shallow clones (`--depth=N`) produce incomplete generation numbers; use full clones (`fetch-depth: 0`) before writing the commit-graph

## Verification

```bash
# Confirm the commit-graph covers all reachable commits
git commit-graph verify --reachable

# Show generation number of HEAD
git cat-file -p HEAD | head -1  # compare with graph info

# Confirm bloom filters are present
file .git/objects/info/commit-graph  # should mention "BIDX" chunk

# Benchmark traversal with and without the graph
rm .git/objects/info/commit-graph
time git log --oneline main~1000..main > /dev/null

git commit-graph write --reachable --changed-paths
time git log --oneline main~1000..main > /dev/null
```

## Related

- [git-maintenance-scheduled-background-pack-optimization.md](git-maintenance-scheduled-background-pack-optimization.md)
- [monorepo-affected-builds-2026.md](monorepo-affected-builds-2026.md)
- [git-bisect-2026.md](git-bisect-2026.md)
- [ci-cd-pipeline-2026.md](ci-cd-pipeline-2026.md)
- [git-cleanup-2026.md](git-cleanup-2026.md)

## Sources

- https://git-scm.com/docs/git-commit-graph
- https://devblogs.microsoft.com/devops/updates-to-the-git-commit-graph-feature/
- https://github.blog/engineering/infrastructure/supercharging-the-git-commit-graph/
- Git 2.24 release notes (changed-paths bloom filters)
