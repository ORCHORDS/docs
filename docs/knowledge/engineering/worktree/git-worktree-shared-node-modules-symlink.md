# Sharing node_modules Across Git Worktrees via Symlink

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have two or more git worktrees for the same project and notice:

- `npm install` in the secondary worktree downloads everything again (hundreds of MB, minutes of time)
- Disk usage doubles or triples with each additional worktree
- Keeping dependency versions in sync between worktrees is error-prone

The fix is to install once in the primary worktree and symlink `node_modules` from all secondary worktrees into the primary's copy.

---

## Context

Node's module resolution walks up the directory tree looking for `node_modules`. A symlink at `<worktree>/node_modules` pointing to the primary's `node_modules` satisfies this resolution without a second install. The approach works for npm, pnpm (with caveats), and Yarn (classic and berry with care).

Native addons (e.g., `esbuild`, `sharp`, `bcrypt`) compiled to a specific Node version and OS are safe to share between worktrees on the same machine. They become a problem only when worktrees run on different architectures or Node versions — avoid the symlink in that case.

---

## Section 1: Creating the Symlink

```bash
# Primary worktree (full install lives here)
cd /path/to/project
npm install  # installs into /path/to/project

# Add a secondary worktree
git worktree add /path/to/project feature/my-feature

# Symlink node_modules into the secondary worktree
ln -s /path/to/project /path/to/project

# Verify resolution
node -e "require.resolve('react')" --prefix /path/to/project
# /path/to/project
```

For multiple worktrees, wrap it in a helper:

```bash
#!/usr/bin/env bash
# scripts/link-node-modules.sh
set -euo pipefail

PRIMARY="$(git worktree list --porcelain | awk 'NR==1{print $2}')"

git worktree list --porcelain \
  | grep '^worktree' \
  | awk '{print $2}' \
  | tail -n +2 \
  | while read -r wt; do
      if [ ! -e "$wt/node_modules" ]; then
        ln -s "$PRIMARY/node_modules" "$wt/node_modules"
        echo "Linked $wt/node_modules -> $PRIMARY/node_modules"
      else
        echo "Skipped $wt/node_modules (already exists)"
      fi
    done
```

```bash
bash scripts/link-node-modules.sh
```

---

## Section 2: npm Resolution Path Details

Node.js resolution (CommonJS `require` and ESM `import` with a loader) follows this chain:

1. Look for `node_modules/<pkg>` in the directory of the importing file.
2. Walk up parent directories repeating step 1.
3. Use `NODE_PATH` entries (rarely needed).

Because the symlink target (`/path/to/project) is resolved **at the OS level before** Node sees the path, Node finds the packages as if they were installed locally. `package.json` workspaces and scoped packages (`@org/pkg`) work correctly because the entire `node_modules` tree is available.

```typescript
// Confirm resolution in TypeScript (run with tsx)
import { createRequire } from "module";
import path from "path";

const require = createRequire(import.meta.url);

const pkgs = ["react", "typescript", "esbuild"];
for (const pkg of pkgs) {
  const resolved = require.resolve(pkg);
  console.log(`${pkg}: ${resolved}`);
}
// react:      /path/to/project
// typescript: /path/to/project
// esbuild:    /path/to/project
```

---

## Section 3: Handling Package Updates Across Worktrees

When `package.json` diverges between branches (e.g., the feature branch adds a new dependency), the symlinked `node_modules` in the secondary worktree won't have that package. Install it in the **primary** worktree:

```bash
# Feature branch added "zod" to package.json but primary doesn't have it
cd /path/to/project          # primary worktree
npm install zod              # installs into shared node_modules

# Now available in all worktrees
node -e "require('zod')" --prefix /path/to/project  # no error
```

For a fully automated approach, add a post-checkout hook that re-runs `npm install` in the primary whenever `package.json` changes:

```bash
# .git/hooks/post-checkout
#!/usr/bin/env bash
PREVIOUS_HEAD="$1"
NEW_HEAD="$2"
IS_BRANCH_CHECKOUT="$3"

if [ "$IS_BRANCH_CHECKOUT" = "1" ]; then
  PRIMARY="$(git worktree list --porcelain | awk 'NR==1{print $2}')"
  if git diff --name-only "$PREVIOUS_HEAD" "$NEW_HEAD" | grep -q 'package.json'; then
    echo "[hook] package.json changed, running npm install in primary worktree..."
    (cd "$PRIMARY" && npm install)
  fi
fi
```

---

## Section 4: pnpm Worktree Compatibility

pnpm uses hard links and a content-addressable store. Its `node_modules/.modules.yaml` contains the virtual store path, which breaks the simple symlink approach. Instead, use pnpm's built-in workspace support:

```yaml
# pnpm-workspace.yaml at the monorepo root
packages:
  - "."
```

Or, share the pnpm store and run `pnpm install` per worktree — it will be fast because packages are hard-linked from the global store (`~/.pnpm-store`), not downloaded again:

```bash
# Each worktree runs its own install but shares the content store
cd /path/to/project
pnpm install  # near-instant; hard-links from ~/.pnpm-store
```

---

## Anti-patterns

- **Symlinking when Node versions differ between worktrees** — native addons (`esbuild`, `sharp`) are compiled for a specific Node ABI; a mismatch causes `Error: invalid ELF header`.
- **Symlinking in a monorepo with workspace hoisting** — the symlink destination's `node_modules` may not include packages that are only in a sub-package's `node_modules`.
- **Committing the symlink** — add `node_modules` to `.gitignore` (it should be there already). The symlink itself must not be committed.
- **Running `npm ci` in the secondary worktree** — `npm ci` deletes `node_modules` before installing, which removes the symlink (and installs a fresh copy). Guard CI scripts to always run from the primary.

---

## Gotchas

- `__dirname` and `import.meta.url` in packages that use `fs` to resolve their own assets may produce paths pointing into the primary worktree's directory, which is usually fine but worth noting.
- Tools that fingerprint `node_modules` paths (e.g., some Jest transform caches) may cache-miss more often because the resolved path is always the primary's path.
- On macOS, `ln -s` relative paths are evaluated from the symlink's location, not CWD. Use absolute paths (as shown above) to avoid confusion.
- Windows NTFS junctions can replace symlinks on Windows: `mklink /J myapp-feat\node_modules myapp\node_modules` — but this is untested with all npm lifecycle scripts.

---

## Verification

```bash
# Confirm the symlink is in place
ls -la /path/to/project
# lrwxrwxrwx ... node_modules -> /path/to/project

# Confirm a package resolves from the secondary worktree
cd /path/to/project
node -e "console.log(require.resolve('lodash'))"
# /path/to/project

# Confirm disk usage has NOT doubled
du -sh /path/to/project
du -sh /path/to/project
# Second line should show ~0 (the symlink itself)
```

---

## Related

- `documentation/docs/policies/worktree/git-worktree-feature-flag-parallel-dev.md`
- `documentation/docs/policies/worktree/git-worktree-sparse-checkout-large-monorepo.md`
- `documentation/docs/policies/worktree/git-worktree-git-hooks-isolation.md`

---

## Sources

- https://nodejs.org/api/modules.html#loading-from-node_modules-folders
- https://git-scm.com/docs/git-worktree
- https://pnpm.io/faq#does-pnpm-work-with-multiple-git-worktrees
- https://docs.npmjs.com/cli/commands/npm-ci
