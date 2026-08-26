# Git Subtree Split: Extracting a Package from a Monorepo

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers package inside a monorepo has grown into a standalone product—its own release cadence, external contributors, and documentation site. You need to extract it into its own repository while keeping the full commit history for that subdirectory, so `git log`, blame, and bisect continue to work in the new repo. `git subtree split` rewrites the monorepo history scoped to a single prefix and produces a branch whose commits contain only the files from that path.

## Context

`git subtree` is a built-in Git command (no external install needed). `git subtree split --prefix=<path>` walks all commits that touched `<path>`, rewrites each one to contain only the files under that path (with paths rebased to the root), and emits a new branch tip. The original monorepo is unchanged. The extracted branch can be pushed to a new remote or used as a seed for a standalone repo. This is the inverse of `git subtree add`, which merges an external repo into a subdirectory.

---

## Step 1 — Audit the Package Boundary

Before splitting, verify that the target package has no import cycles into sibling packages that would break when extracted:

```typescript
// scripts/audit-package-boundary.ts
import { execSync } from "child_process";
import * as path from "path";

const TARGET = process.argv[2] ?? "packages/my-worker";

const allImports = execSync(
  `grep -r --include="*.ts" "from '" ${TARGET}/src`,
  { encoding: "utf8" }
)
  .split("\n")
  .filter(Boolean);

const crossPackageImports = allImports.filter((line) => {
  // Flag any import that references a sibling path like ../../packages/other
  return line.includes("../../packages/") || line.includes("@repo/");
});

if (crossPackageImports.length > 0) {
  console.error("Cross-package imports found — resolve before splitting:");
  crossPackageImports.forEach((l) => console.error(" ", l));
  process.exit(1);
}

console.log(`${TARGET}: package boundary is clean`);
```

## Step 2 — Perform the Subtree Split

```bash
#!/usr/bin/env bash
set -euo pipefail

MONOREPO_ROOT=$(git rev-parse --show-toplevel)
PACKAGE_PATH="packages/my-worker"          # relative to monorepo root
NEW_BRANCH="extracted/my-worker"
NEW_REMOTE="git@github.com:org/my-worker.git"

cd "$MONOREPO_ROOT"

# Split: rewrites all commits that touched PACKAGE_PATH
# This can take minutes on large repos — add --rejoin to cache intermediate work
git subtree split \
  --prefix="$PACKAGE_PATH" \
  --branch="$NEW_BRANCH" \
  --annotate="(split from monorepo) "

echo "Split complete. Branch: $NEW_BRANCH"
echo "First commit on branch:"
git log --oneline "$NEW_BRANCH" | tail -1

# Push to the new standalone repo
git push "$NEW_REMOTE" "${NEW_BRANCH}:main"
```

## Step 3 — Bootstrap the Standalone Repo

The extracted branch contains only the package files. Set up the standalone repo with its own tooling:

```bash
#!/usr/bin/env bash
# Run this inside the NEW standalone repo after cloning
MONOREPO_REMOTE="git@github.com:org/monorepo.git"
PACKAGE_PATH="packages/my-worker"

# Add monorepo as a remote so future cherry-picks are easy
git remote add monorepo "$MONOREPO_REMOTE"
git fetch monorepo --no-tags

# Create a local branch that tracks the split branch
git checkout -b monorepo-sync monorepo/extracted/my-worker

echo "Standalone repo bootstrapped."
echo "Run 'git log --oneline' to verify history depth."
```

## Step 4 — Wire Wrangler for the Standalone Repo

The extracted package likely had its `wrangler.toml` scoped to the monorepo root. Update it for standalone operation:

```toml
# wrangler.toml (standalone repo root — formerly packages/my-worker/wrangler.toml)
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2026-08-01"

# Previously referenced shared packages via workspace protocol — now use npm
# Replace @repo/utils with the published npm package or inline the code

[vars]
ENVIRONMENT = "production"

[[d1_databases]]
binding = "DB"
database_name = "my-worker-prod"
database_id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

```typescript
// scripts/verify-standalone-build.ts
// Confirm the package builds without monorepo workspace dependencies
import { execSync } from "child_process";

try {
  execSync("npx wrangler deploy --dry-run --outdir dist-check", {
    stdio: "inherit",
  });
  console.log("Standalone build: OK");
} catch {
  console.error(
    "Build failed — likely a workspace dependency that needs publishing first"
  );
  process.exit(1);
}
```

## Step 5 — Keep Histories in Sync with --rejoin

For a long-running split (trunk is still active in both repos), use `--rejoin` to cache the split work as a merge commit so subsequent splits only process new commits:

```bash
#!/usr/bin/env bash
# Run periodically in the monorepo to surface new commits in the standalone repo
PACKAGE_PATH="packages/my-worker"
NEW_BRANCH="extracted/my-worker"

# --rejoin creates a merge commit that marks the split point,
# making future splits much faster (only new commits are processed)
git subtree split \
  --prefix="$PACKAGE_PATH" \
  --branch="$NEW_BRANCH" \
  --rejoin

# Cherry-pick new commits into the standalone repo
STANDALONE_REMOTE="git@github.com:org/my-worker.git"
NEW_TIP=$(git rev-parse "$NEW_BRANCH")
git push "$STANDALONE_REMOTE" "${NEW_BRANCH}:inbound-sync"

echo "New tip pushed to standalone inbound-sync branch: $NEW_TIP"
echo "Open a PR in the standalone repo to review before merging."
```

## Automating in CI (GitHub Actions)

```yaml
# .github/workflows/subtree-sync.yml
name: Sync extracted package
on:
  push:
    branches: [main]
    paths:
      - "packages/my-worker/**"

jobs:
  subtree-split:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history required for subtree split

      - name: Configure git
        run: |
          git config user.email "ci@example.com"
          git config user.name "CI Bot"

      - name: Split and push
        env:
          STANDALONE_DEPLOY_KEY: ${{ secrets.STANDALONE_DEPLOY_KEY }}
        run: |
          eval "$(ssh-agent -s)"
          echo "$STANDALONE_DEPLOY_KEY" | ssh-add -
          git subtree split \
            --prefix=packages/my-worker \
            --branch=extracted/my-worker \
            --rejoin
          git push git@github.com:org/my-worker.git extracted/my-worker:main
```

---

## Anti-patterns

- **Splitting without `--rejoin` on active repos.** Every subsequent split reprocesses the full history. On a monorepo with thousands of commits this takes minutes per run. Always `--rejoin` after the first split.
- **Leaving workspace-protocol dependencies unresolved.** `@repo/utils` won't resolve in the standalone repo. Either publish shared packages to npm first or inline the code before splitting.
- **Splitting a path with inconsistent casing across history.** Git on case-insensitive filesystems (macOS, Windows) may produce a corrupted split if the path changed case mid-history. Audit with `git log --diff-filter=R -- packages/MyWorker packages/my-worker`.
- **Forgetting `fetch-depth: 0` in CI.** A shallow clone makes `git subtree split` fail with "fatal: ambiguous argument". Always fetch full history.

## Gotchas

- `git subtree split` is `O(n)` in the number of commits that touched the prefix. A 5-year-old monorepo with 50k commits can take 10–15 minutes for the first split.
- The `--annotate` flag prepends a string to every rewritten commit message. Use it to mark split commits so they're identifiable in the standalone repo's `git log`.
- Binary files committed to the monorepo (even outside the split prefix) are included in the pack objects that Git downloads. If the monorepo has git LFS pointers, the standalone repo will also get pointers without the LFS objects. Migrate binaries to Cloudflare R2 before splitting.
- `git subtree` does not update `.git/info/grafts`. If the monorepo used grafts or replace refs, the split history may differ from what `git log` shows locally.

## Verification

```bash
# 1. Confirm commit count in extracted branch
git log --oneline extracted/my-worker | wc -l

# 2. Confirm no cross-package paths leaked into the split
git show extracted/my-worker:. | head -20
# Should only show files from packages/my-worker/, not sibling packages

# 3. Verify a file's blame traces correctly in the standalone repo
cd /tmp/standalone-my-worker
git log --follow --oneline -- src/index.ts | head -10

# 4. Dry-run Wrangler deploy from standalone repo
wrangler deploy --dry-run
```

## Related

- `git-submodules-subtrees-2026.md`
- `git-submodules-vs-subtrees.md`
- `monorepo-pnpm-turborepo-2026.md`
- `git-lfs-r2-large-asset-migration.md`
- `wrangler-config-inheritance-environments-workers.md`

## Sources

- Git documentation: `git-subtree(1)`
- GitHub Blog: "Working with subtrees" https://github.blog/open-source/git/working-with-subtree-in-git/
- Wrangler configuration reference: https://developers.cloudflare.com/workers/wrangler/configuration/
