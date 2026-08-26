# Git Worktree Lockfile Isolation with pnpm

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Two git worktrees running `pnpm install` simultaneously corrupt or overwrite each other's `node_modules` because pnpm's virtual store is shared by default, causing cryptic module resolution errors and broken test runs.

## Context
`git worktree add` creates additional working trees that share the same `.git` directory and, by default, the same `node_modules/.pnpm` virtual store. When two worktrees install different dependency sets — for instance, a `main` worktree pinned to `[email protected]` and a `feature` worktree testing `[email protected]` — pnpm's content-addressable store can interleave writes, leaving hard-link targets inconsistent. The solution is to configure each worktree with an isolated virtual store root via `.npmrc` or pnpm workspace settings, while still sharing the global content store for download efficiency.

## pnpm Isolation Strategy
```bash
# In the primary worktree (the main repo root)
# .npmrc
virtual-store-dir=.pnpm-store
store-dir=~/.pnpm-store   # global cache shared across all worktrees

# Each worktree gets its own .npmrc via a worktree-level override
# This prevents cross-worktree node_modules contamination
```

```bash
# Worktree provisioning script
# scripts/new-worktree.sh
#!/usr/bin/env bash
set -euo pipefail

BRANCH="${1:?Usage: new-worktree.sh <branch> [<path>]}"
WORKTREE_PATH="${2:-../worktrees/$BRANCH}"

# Create the worktree
git worktree add "$WORKTREE_PATH" "$BRANCH"

# Inject a worktree-local .npmrc that isolates its virtual store
cat > "$WORKTREE_PATH/.npmrc" <<NPMRC
virtual-store-dir=.pnpm-store
store-dir=${HOME}/.pnpm-store
NPMRC

echo "Worktree created at $WORKTREE_PATH"
echo "Run: cd $WORKTREE_PATH && pnpm install"
```

## Worktree-scoped .npmrc with Automatic Path
```ini
# .npmrc placed in each worktree root at creation time
# The virtual-store-dir is relative to the worktree root,
# so each worktree gets its own isolated node_modules/.pnpm
virtual-store-dir=node_modules/.pnpm
store-dir=~/.local/share/pnpm/store/v10
shamefully-hoist=false
```

## TypeScript Helper: Worktree Status with Dependency Drift
```typescript
// scripts/worktree-health.ts
import { execSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

interface WorktreeInfo {
  path: string;
  branch: string;
  hasNpmrc: boolean;
  lockfileSha: string | null;
}

function getWorktrees(): WorktreeInfo[] {
  const raw = execSync("git worktree list --porcelain", { encoding: "utf8" });
  const trees: WorktreeInfo[] = [];
  let current: Partial<WorktreeInfo> = {};

  for (const line of raw.split("\n")) {
    if (line.startsWith("worktree ")) {
      if (current.path) trees.push(current as WorktreeInfo);
      current = { path: line.slice(9).trim() };
    } else if (line.startsWith("branch ")) {
      current.branch = line.slice(7).replace("refs/heads/", "").trim();
    }
  }
  if (current.path) trees.push(current as WorktreeInfo);

  return trees.map((t) => {
    const npmrcPath = join(t.path, ".npmrc");
    const lockPath = join(t.path, "pnpm-lock.yaml");
    return {
      ...t,
      hasNpmrc: existsSync(npmrcPath),
      lockfileSha: existsSync(lockPath)
        ? execSync(`sha256sum "${lockPath}"`, { encoding: "utf8" })
            .split(" ")[0]
            .slice(0, 8)
        : null,
    };
  });
}

const trees = getWorktrees();
console.table(trees);

const missingNpmrc = trees.filter((t) => !t.hasNpmrc);
if (missingNpmrc.length > 0) {
  console.error(
    "Worktrees missing .npmrc isolation:",
    missingNpmrc.map((t) => t.path)
  );
  process.exit(1);
}
```

## CI: Per-worktree Cache Isolation in GitHub Actions
```yaml
# .github/workflows/parallel-worktree-test.yml
name: Parallel worktree tests

on:
  pull_request:

jobs:
  matrix-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        suite: [unit, integration, e2e]
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
        with:
          version: 10

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
          # Cache key includes the matrix value so each suite gets
          # its own restored node_modules snapshot
          cache-dependency-path: pnpm-lock.yaml

      - name: Install (isolated virtual store)
        run: |
          echo "virtual-store-dir=node_modules/.pnpm" >> .npmrc
          echo "store-dir=$HOME/.pnpm-store" >> .npmrc
          pnpm install --frozen-lockfile

      - name: Run suite
        run: pnpm vitest run --project=${{ matrix.suite }}
```

## Makefile Convenience Targets
```makefile
# Makefile
WORKTREES_DIR := ../worktrees

.PHONY: worktree-add worktree-list worktree-clean

worktree-add: ## Add an isolated worktree: make worktree-add BRANCH=feature/foo
    @bash scripts/new-worktree.sh "$(BRANCH)" "$(WORKTREES_DIR)/$(BRANCH)"
    @cd "$(WORKTREES_DIR)/$(BRANCH)" && pnpm install --frozen-lockfile

worktree-list: ## List all worktrees with their isolation status
    @pnpm tsx scripts/worktree-health.ts

worktree-clean: ## Remove all non-main worktrees and their node_modules
    @git worktree list --porcelain \
      | grep '^worktree ' \
      | awk '{print $$2}' \
      | tail -n +2 \
      | xargs -I{} bash -c 'rm -rf "{}"/node_modules && git worktree remove "{}" --force'
```

## Anti-patterns
- Sharing a single `node_modules` between two worktrees by symlinking — symlinks bypass worktree isolation and cause hard-to-debug resolution errors
- Running `pnpm install --no-frozen-lockfile` in a worktree to resolve a conflict — this mutates the shared `pnpm-lock.yaml` and can invalidate the primary worktree's install
- Using `npm` or `yarn` in one worktree when the project uses `pnpm` — lockfile format conflicts corrupt dependency state
- Deleting a worktree with `rm -rf` without first calling `git worktree remove` — orphaned `.git/worktrees/<id>` entries remain and confuse `git worktree list`

## Gotchas
- The global pnpm content store (`~/.pnpm-store`) is safe to share between worktrees — only the virtual store (symlink farm in `node_modules/.pnpm`) needs isolation
- `pnpm-lock.yaml` is a single file tracked by the repository; editing it in one worktree creates a dirty state visible in all others
- If `.npmrc` is committed to the repository, a worktree-level override file takes precedence only if its `virtual-store-dir` path is relative (resolved relative to the worktree root, not the main worktree)
- After `git worktree remove`, pnpm's virtual store directory under the removed path may persist; always `rm -rf` the worktree directory afterward

## Verification
```bash
# Verify each worktree has its own virtual store
git worktree list --porcelain \
  | grep '^worktree' \
  | awk '{print $2}' \
  | xargs -I{} ls -la "{}"/node_modules/.pnpm 2>/dev/null | head -20

# Confirm installs do not cross-contaminate
pnpm tsx scripts/worktree-health.ts

# Run the full test suite in each worktree and compare output
for wt in ../worktrees/*/; do
  echo "=== $wt ===" && (cd "$wt" && pnpm test --silent)
done
```

## Related
- `/documentation/docs/policies/worktree/git-worktree-2026.md`
- `/documentation/docs/policies/worktree/git-worktree-best-practices.md`
- `/documentation/docs/policies/worktree/git-worktree-specific-configuration-boundaries.md`
- `/documentation/docs/policies/worktree/monorepo-pnpm-turborepo-2026.md`
- `/documentation/docs/policies/worktree/pnpm-catalog-monorepo-dependency-alignment.md`

## Sources
- https://pnpm.io/npmrc#virtual-store-dir
- https://git-scm.com/docs/git-worktree
- https://pnpm.io/cli/install#--frozen-lockfile
