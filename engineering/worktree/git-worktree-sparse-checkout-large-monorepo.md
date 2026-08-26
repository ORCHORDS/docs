# Sparse Checkout in Worktrees for Large Monorepos

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your monorepo contains hundreds of packages, dozens of apps, and gigabytes of generated assets. When you add a git worktree to work on a specific app or package, the worktree checks out the entire tree — including thousands of files you will never touch. The result:

- `git status` takes 5-10 seconds
- `git add` and `git commit` are sluggish
- Editor file watchers (VS Code, Webpack, Vite) churn on irrelevant directories
- Wrangler's file-change detection for Workers triggers on unrelated packages

Combining **git sparse-checkout** with **git worktrees** lets each worktree materialize only the subset of the tree it needs.

---

## Context

Sparse checkout (introduced in Git 2.25, cone mode in 2.26) tells Git which directories to populate in the working tree. The object database still holds the full history; sparse-checkout only controls what appears on disk. When applied per-worktree, each worktree gets its own sparse pattern, completely independent of the primary worktree.

This is especially useful for:
- Wrangler monorepos where you work on one Worker at a time
- Next.js / Turborepo monorepos with 20+ apps
- Large open-source contributors who only touch a sub-tree

---

## Section 1: Enabling Sparse-Checkout in Cone Mode

Cone mode restricts the pattern language to directory prefixes, which enables bitmap-accelerated walks and is significantly faster than the legacy pattern mode.

```bash
# In the primary worktree (or any existing worktree)
# Enable sparse checkout
git sparse-checkout init --cone

# Set which directories to materialize (always includes root files)
git sparse-checkout set packages/payments-worker packages/shared-utils

# Confirm
git sparse-checkout list
# packages/payments-worker
# packages/shared-utils
```

After this, only `packages/payments-worker/` and `packages/shared-utils/` (plus root-level files) are present on disk.

```bash
# Verify
ls packages/
# payments-worker  shared-utils
# (all other packages absent)
```

---

## Section 2: Per-Worktree Sparse Patterns

Each worktree stores its own sparse-checkout config. The pattern file lives at:

```
.git/worktrees/<worktree-name>/info/sparse-checkout
```

or for the main worktree:

```
.git/info/sparse-checkout
```

```bash
# Add a second worktree for a different Worker
git worktree add /path/to/project feature/auth-worker

# Configure sparse checkout INSIDE that worktree
cd /path/to/project
git sparse-checkout init --cone
git sparse-checkout set packages/auth-worker packages/shared-utils

# Return to primary
cd /path/to/project
git sparse-checkout list
# packages/payments-worker
# packages/shared-utils   ← still unchanged

cd /path/to/project
git sparse-checkout list
# packages/auth-worker
# packages/shared-utils   ← independent patterns
```

---

## Section 3: Wrangler Monorepo Use Case

A typical Cloudflare Workers monorepo might look like:

```
monorepo/
  packages/
    api-gateway/       wrangler.toml
    auth-worker/       wrangler.toml
    payments-worker/   wrangler.toml
    shared-utils/      (no wrangler.toml, imported by others)
    assets/            (large static files, ~2 GB)
  package.json
  turbo.json
```

Spinning up a worktree for `payments-worker` without `assets/` and the other Worker packages:

```bash
git worktree add /path/to/project feature/update-stripe
cd /path/to/project
git sparse-checkout init --cone
git sparse-checkout set packages/payments-worker packages/shared-utils

# Wrangler now only watches the materialized files
cd packages/payments-worker
wrangler dev
# File watching: packages/payments-worker, packages/shared-utils — fast!
```

```bash
# scripts/worktree-sparse-add.sh
# Usage: bash scripts/worktree-sparse-add.sh <path> <branch> <pkg1> [<pkg2> ...]
set -euo pipefail

WT_PATH="$1"; shift
BRANCH="$1"; shift
PKGS=("$@")

git worktree add "$WT_PATH" "$BRANCH"
(
  cd "$WT_PATH"
  git sparse-checkout init --cone
  git sparse-checkout set "${PKGS[@]}"
  echo "Sparse patterns set: ${PKGS[*]}"
  echo "Files on disk:"
  ls -d packages/*/
)
```

```bash
bash scripts/worktree-sparse-add.sh \
  /path/to/project \
  feature/update-stripe \
  packages/payments-worker \
  packages/shared-utils
```

---

## Section 4: Faster Clone for CI with Partial Clone + Sparse Checkout

For ephemeral CI environments, combine `--filter=blob:none` (partial clone) with sparse checkout to minimize download size:

```bash
# CI pipeline step
git clone --filter=blob:none --no-checkout \
  https://github.com/org/monorepo.git /workspace/monorepo

cd /workspace/monorepo
git sparse-checkout init --cone
git sparse-checkout set packages/payments-worker packages/shared-utils
git checkout main

# Only blobs for the materialized paths are fetched
# Object store download: ~50 MB instead of ~2 GB
```

```typescript
// scripts/ci-sparse-setup.ts
// Used in GitHub Actions / Cloudflare CI to configure sparse checkout
import { execSync } from "child_process";

const WORKER_PACKAGES: Record<string, string[]> = {
  "payments-worker": ["packages/payments-worker", "packages/shared-utils"],
  "auth-worker": ["packages/auth-worker", "packages/shared-utils"],
  "api-gateway": ["packages/api-gateway", "packages/shared-utils"],
};

function run(cmd: string): string {
  return execSync(cmd, { encoding: "utf8", stdio: ["pipe", "pipe", "inherit"] });
}

const target = process.env.WORKER_TARGET;
if (!target) throw new Error("WORKER_TARGET env var is required");

const pkgs = WORKER_PACKAGES[target];
if (!pkgs) throw new Error(`Unknown WORKER_TARGET: ${target}`);

run("git sparse-checkout init --cone");
run(`git sparse-checkout set ${pkgs.join(" ")}`);

console.log(`Sparse checkout configured for ${target}:`);
console.log(run("git sparse-checkout list"));
console.log("Disk usage:");
console.log(run("du -sh packages/"));
```

---

## Anti-patterns

- **Using legacy (non-cone) mode for a worktree in a large repo** — pattern matching is O(files) and causes the same slow `git status` you are trying to avoid; always use `--cone`.
- **Adding a new package to `sparse-checkout set` on only one worktree and expecting it to appear in others** — sparse patterns are per-worktree; update each explicitly.
- **Running `git checkout .` to reset files** — in sparse-checkout mode this also re-materializes all excluded files temporarily; use `git restore` instead.
- **Using `git add .` when some expected files are absent** — sparse checkout intentionally omits directories; `git add .` will not stage changes in omitted paths, which is correct but can be surprising.

---

## Gotchas

- `git sparse-checkout disable` removes the sparse config and materializes the full tree. Running it accidentally in a large monorepo can write gigabytes of files to disk.
- Some tools (e.g., `turbo run build --filter=...`) need to see the full `package.json` of all workspace packages to build the task graph even if only one package is being built. Add the minimal set of root-level files each tool needs.
- `git worktree add` with `--no-checkout` creates the worktree directory without materializing any files — then you can configure sparse-checkout before the first checkout:

```bash
git worktree add --no-checkout /path/to/project feature/auth-worker
cd /path/to/project
git sparse-checkout init --cone
git sparse-checkout set packages/auth-worker packages/shared-utils
git checkout feature/auth-worker  # now materializes only the sparse set
```

- GitHub's partial clone (`--filter=blob:none`) does not affect existing clones; for existing repos, blob fetches happen lazily on access.

---

## Verification

```bash
# Confirm sparse patterns are active and correct
git sparse-checkout list
# packages/payments-worker
# packages/shared-utils

# Confirm excluded packages are absent
ls packages/ | grep -v -E "payments-worker|shared-utils"
# (should produce no output)

# Measure git status speed
time git status
# real    0m0.3s  (vs 8s for the full tree)

# Confirm Wrangler still finds the worker
cd packages/payments-worker
wrangler dev --dry-run
# Should succeed without errors about missing files
```

---

## Related

- `documentation/categories/worktree/git-worktree-feature-flag-parallel-dev.md`
- `documentation/categories/worktree/git-worktree-shared-node-modules-symlink.md`
- `documentation/categories/worktree/git-worktree-git-hooks-isolation.md`

---

## Sources

- https://git-scm.com/docs/git-sparse-checkout
- https://git-scm.com/docs/git-worktree
- https://github.blog/2020-01-17-bring-your-monorepo-down-to-size-with-sparse-checkout/
- https://developers.cloudflare.com/workers/wrangler/
- https://turbo.build/repo/docs/crafting-your-repository/structuring-a-repository
