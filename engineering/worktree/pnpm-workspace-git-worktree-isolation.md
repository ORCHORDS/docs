# pnpm Workspace and Git Worktree Node Modules Isolation

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You add a second git worktree for a hotfix branch alongside your main worktree, then run
`pnpm install` inside it. Immediately after, your primary worktree's TypeScript server
loses types, Wrangler throws "package not found" errors, and running tests in either
worktree produces inconsistent results. The root cause is that both worktrees share a
single `node_modules` directory and a single pnpm virtual store, so concurrent installs
corrupt each other's symlink graph.

## Context

`git worktree add` clones the working tree into a new directory but does NOT clone
`node_modules`. Both the main worktree and linked worktrees share the same
`.git` directory and therefore, if placed as siblings on disk, often end up sharing the
same `pnpm-lock.yaml` and the same nearest-ancestor `node_modules`. In a pnpm workspace
monorepo this is especially fragile because the virtual store at
`<root>/node_modules/.pnpm` is a flat, content-addressed cache. Two concurrent `pnpm
install` runs targeting the same store produce race conditions on hard-link creation.

The fix is to either (a) give each worktree its own isolated `node_modules` via
`.npmrc`'s `virtual-store-dir`, or (b) use a shared read-only store with per-worktree
symlink trees. Option (a) is simpler; option (b) saves disk space at the cost of
coordination.

## Option A: Per-Worktree Virtual Store via .npmrc Override

```bash
# Add a worktree outside the main repo tree so it doesn't inherit the root .npmrc
git worktree add ../my-repo-hotfix origin/hotfix/pay-503

# Create a worktree-local .npmrc that redirects pnpm's virtual store
cat > ../my-repo-hotfix/.npmrc <<'EOF'
# Isolate this worktree's node_modules from the primary worktree
virtual-store-dir=.pnpm-store
shamefully-hoist=false
EOF

# Install into the isolated store
cd ../my-repo-hotfix
pnpm install --frozen-lockfile
```

```
# Directory layout after the above
my-repo/            ← main worktree
  node_modules/
    .pnpm/          ← main virtual store
  .npmrc            ← root config (no virtual-store-dir override)

my-repo-hotfix/     ← linked worktree
  .pnpm-store/      ← isolated virtual store for this worktree only
  node_modules/
  .npmrc            ← local override
```

## Option B: Shared Content-Addressed Store, Per-Worktree Symlink Trees

```ini
# pnpm-workspace.yaml root .npmrc — shared store on a fast disk
store-dir=/data/pnpm-store          # shared across all worktrees on the machine
virtual-store-dir=node_modules/.pnpm  # per-worktree (relative = per-directory)
```

```bash
# Each worktree installs into its own node_modules/.pnpm
# but all hard-links point into the shared /data/pnpm-store
# Zero byte duplication; no cross-worktree corruption

# Main worktree
cd my-repo && pnpm install --frozen-lockfile

# Hotfix worktree — separate node_modules/.pnpm, shared store
cd ../my-repo-hotfix && pnpm install --frozen-lockfile
```

## Automating Worktree Setup with install in CI

```bash
#!/usr/bin/env bash
# scripts/worktree-new.sh — creates a worktree and installs deps
set -euo pipefail

BRANCH="${1:?usage: worktree-new.sh <branch> [path]}"
DEST="${2:-../${BRANCH//\//-}}"

git worktree add "$DEST" "$BRANCH"

# Write a worktree-local .npmrc so pnpm is isolated
cat > "$DEST/.npmrc" <<EOF
virtual-store-dir=.pnpm-store
EOF

echo "Installing dependencies in $DEST …"
(cd "$DEST" && pnpm install --frozen-lockfile)

echo "Worktree ready: $DEST"
```

```bash
# Tear down: remove node_modules before pruning the worktree to avoid
# leaving orphaned hard-links in the shared pnpm store
scripts/worktree-remove.sh ../my-repo-hotfix
```

```bash
#!/usr/bin/env bash
# scripts/worktree-remove.sh
set -euo pipefail
TARGET="${1:?usage: worktree-remove.sh <path>}"
rm -rf "$TARGET/node_modules" "$TARGET/.pnpm-store"
git worktree remove --force "$TARGET"
```

## TypeScript Project References Across Worktrees

```jsonc
// tsconfig.json in each worktree package — use relative paths, not symlinks
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@repo/utils": ["../../packages/utils/src"]
    }
  },
  "references": [{ "path": "../../packages/utils" }]
}
```

```bash
# Build composite projects from the worktree root, not the main root
# so tsc uses the worktree's own node_modules
cd ../my-repo-hotfix
pnpm -r run build          # each workspace package builds with its own node_modules
```

## Wrangler Dev Inside an Isolated Worktree

```bash
# No special config needed — wrangler resolves packages from the worktree's
# own node_modules because the CWD is the worktree root
cd ../my-repo-hotfix/apps/worker-payments
pnpm wrangler dev          # uses hotfix deps, not main-branch deps
```

```toml
# wrangler.toml — no path adjustments needed; wrangler reads from CWD
name = "worker-payments"
main = "src/index.ts"
compatibility_date = "2026-01-01"
```

## Anti-patterns

- Placing the hotfix worktree as a subdirectory *inside* the main repo root. pnpm's
  node_modules resolution walks up the directory tree, so the nested worktree will find
  the parent's `node_modules` first, defeating isolation.
- Committing the worktree-local `.npmrc` to the branch. This `.npmrc` is only meaningful
  on developer machines; adding it to version control confuses CI. Add `/.npmrc` to the
  worktree's local `.gitignore` or use `git update-index --assume-unchanged .npmrc`.
- Running `pnpm install` in both worktrees simultaneously when they share a
  `virtual-store-dir`. pnpm's store locking is per-store, not per-project; concurrent
  runs into the same store still race.
- Forgetting to delete `node_modules` before `git worktree remove`. The stale
  hard-links do not consume extra disk space (content-addressed) but the dangling
  symlinks inside `node_modules/.pnpm` will confuse future `pnpm install` runs in the
  shared store.

## Gotchas

- `.npmrc` files are merged from the global → per-project → per-worktree levels. A
  `virtual-store-dir` in the main repo's root `.npmrc` will be overridden by the
  worktree-local one only if the worktree-local file is loaded first. Verify with
  `pnpm config list` from inside each worktree.
- `pnpm-lock.yaml` is shared across all worktrees on the same branch history. If the
  hotfix branch diverges on `pnpm-lock.yaml`, both worktrees will complain about an
  out-of-date lockfile until you run `pnpm install --no-frozen-lockfile` in each.
- Turborepo's remote cache key includes the monorepo root. If the hotfix worktree is
  at a different absolute path, Turbo will compute different cache keys and miss the
  remote cache. Set `TURBO_REMOTE_CACHE_SIGNATURE_KEY` consistently across worktrees.

## Verification

```bash
# Confirm each worktree has its own virtual store
ls -d my-repo/node_modules/.pnpm
ls -d my-repo-hotfix/.pnpm-store

# Confirm pnpm resolves the correct node_modules from each worktree
(cd my-repo && pnpm ls --depth=0)
(cd my-repo-hotfix && pnpm ls --depth=0)

# Confirm no cross-worktree symlinks exist
find my-repo-hotfix/node_modules -type l -ls | grep "my-repo/" | head -5
# Expected: no output
```

## Related

- `git-worktree-lockfile-isolation.md`
- `monorepo-pnpm-turborepo-2026.md`
- `pnpm-catalog-monorepo-dependency-alignment.md`
- `git-worktree-specific-configuration-boundaries.md`
- `pnpm-workspace-protocol-version-resolution.md`

## Sources

- pnpm virtual-store-dir docs: https://pnpm.io/npmrc#virtual-store-dir
- pnpm store-dir docs: https://pnpm.io/npmrc#store-dir
- Git worktree man page: https://git-scm.com/docs/git-worktree
