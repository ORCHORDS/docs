# Git Sparse-Checkout Cone Mode for Cloudflare Workers Monorepos

- Date: 2026-08-22
- Author: example.com
- Status: production

## Checking Out Only the Workers You Need

A Cloudflare Workers monorepo with 50+ services and shared libraries can exceed 2 GB of working tree. Every CI job that clones the full tree to deploy a single Worker wastes minutes on I/O and bandwidth. Git sparse-checkout in cone mode solves this by materialising only a curated subset of directories into the working tree while keeping the full object store (or using partial clone) in the background.

Cone mode is the fast path: instead of evaluating arbitrary pathspec patterns for every file, it restricts the sparse set to a collection of directory prefixes. Git can answer "is this path included?" with a simple string-prefix check, which is O(1) per file rather than O(patterns). For repos with tens of thousands of files the speed difference is substantial.

The pattern is: `git clone --filter=blob:none --no-checkout`, then `git sparse-checkout init --cone`, then declare exactly which packages you need, then `git checkout`. The checkout step only materialises blobs for the selected directories on demand.

## Context

Stack: Cloudflare Workers monorepo, pnpm workspaces, Turborepo, GitHub Actions. Repository layout uses `workers/<name>/` for Worker source and `packages/<name>/` for shared libraries. CI needs to deploy only the Workers affected by a pull request.

## Enabling Sparse-Checkout Cone Mode

```bash
# Clone with partial blob download (no blobs until checkout)
git clone \
  --filter=blob:none \
  --no-checkout \
  --depth=1 \
  git@github.com:example-org/example-repo.git \
  monorepo
cd monorepo

# Initialise cone mode
git sparse-checkout init --cone

# Declare which directories to materialise.
# The root directory is always included (package.json, pnpm-workspace.yaml, turbo.json, etc.)
git sparse-checkout set \
  workers/api-gateway \
  workers/auth-service \
  packages/shared-utils \
  packages/hono-middleware

# Now checkout: only the declared directories are written to disk
git checkout main

# Inspect what is materialised
git sparse-checkout list
```

The `sparse-checkout` file lives at `.git/info/sparse-checkout`. In cone mode Git also maintains a derived set of "parent" directories (shown read-only) so directory listings look clean.

## Pattern File for Affected-Only Builds

In CI you want to compute the affected set dynamically. The following shell script derives the sparse set from Turborepo's affected-package list and writes it before checkout.

```bash
#!/usr/bin/env bash
# scripts/ci-sparse-set.sh
# Usage: called after git clone --filter=blob:none --no-checkout

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
BASE_SHA="${1:-origin/main}"

# Use Turborepo to list packages touched since BASE_SHA
# turbo ls --filter=...[<sha>] lists affected packages
AFFECTED=$(pnpm turbo ls --filter="...[${BASE_SHA}]" --output=json \
  | jq -r '.packages[].path' 2>/dev/null || true)

if [[ -z "$AFFECTED" ]]; then
  echo "No affected packages detected; checking out everything"
  git sparse-checkout disable
  exit 0
fi

# Build the sparse-checkout set
SPARSE_DIRS=()
while IFS= read -r pkg_path; do
  SPARSE_DIRS+=("$pkg_path")
done <<< "$AFFECTED"

git sparse-checkout init --cone
git sparse-checkout set "${SPARSE_DIRS[@]}"
echo "Sparse set: ${SPARSE_DIRS[*]}"
```

## CI Setup for Affected-Only Workers Builds

```yaml
# .github/workflows/deploy-affected-workers.yml
name: Deploy Affected Workers

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

    steps:
      - name: Partial clone (no blobs yet)
        run: |
          git clone \
            --filter=blob:none \
            --no-checkout \
            --depth=50 \
            "https://x-access-token:${{ secrets.GITHUB_TOKEN }}@github.com/${{ github.repository }}.git" \
            repo
          cd repo
          git sparse-checkout init --cone

      - name: Compute affected set and set sparse dirs
        working-directory: repo
        run: |
          BASE_SHA="${{ github.event.before }}"
          # Fetch just the tree objects needed for pnpm workspace resolution
          git checkout "${{ github.sha }}" -- pnpm-workspace.yaml turbo.json package.json
          bash scripts/ci-sparse-set.sh "$BASE_SHA"
          git checkout "${{ github.sha }}"

      - name: Install pnpm
        uses: pnpm/action-setup@v4
        with:
          version: 9

      - name: Install dependencies (sparse workspace)
        working-directory: repo
        run: pnpm install --frozen-lockfile

      - name: Build affected Workers
        working-directory: repo
        run: pnpm turbo build --filter="...[origin/main^1]"

      - name: Deploy affected Workers
        working-directory: repo
        run: |
          # Enumerate materialised workers/ subdirs and deploy each
          for worker_dir in workers/*/; do
            [[ -f "${worker_dir}wrangler.toml" ]] || continue
            worker_name=$(basename "$worker_dir")
            echo "Deploying $worker_name"
            pnpm --filter "$worker_name" exec wrangler deploy \
              --config "${worker_dir}wrangler.toml"
          done
```

## Workers Selective Deploy with Sparse-Checkout

When deploying from a local machine or a hot-path CI job, you can layer sparse-checkout with `wrangler deploy --dry-run` to validate before committing bandwidth.

```typescript
// scripts/deploy-sparse.ts
// Run with: npx tsx scripts/deploy-sparse.ts --env production

import { execSync } from "node:child_process";
import { readdirSync, existsSync } from "node:fs";
import { join } from "node:path";

const ENV = process.argv.includes("--env")
  ? process.argv[process.argv.indexOf("--env") + 1]
  : "staging";

const DRY_RUN = process.argv.includes("--dry-run");

// List only materialised worker directories (sparse-checkout only writes
// directories that were explicitly set — absent dirs have no entry at all)
const workersRoot = join(process.cwd(), "workers");
const workers = readdirSync(workersRoot, { withFileTypes: true })
  .filter((d) => d.isDirectory())
  .map((d) => d.name);

for (const worker of workers) {
  const configPath = join(workersRoot, worker, "wrangler.toml");
  if (!existsSync(configPath)) {
    console.log(`Skipping ${worker}: no wrangler.toml`);
    continue;
  }
  const cmd = [
    "wrangler deploy",
    `--config ${configPath}`,
    `--env ${ENV}`,
    DRY_RUN ? "--dry-run" : "",
  ]
    .filter(Boolean)
    .join(" ");

  console.log(`[${worker}] ${cmd}`);
  execSync(cmd, { stdio: "inherit" });
}
```

## Anti-patterns

- Running `git sparse-checkout disable` at the end of a CI job and then re-enabling: just clone fresh per job
- Using non-cone mode (plain pathspec patterns) for performance-sensitive CI: it is O(patterns × files), which stalls on large trees
- Forgetting root files: cone mode always materialises root-level files; do not add extra `git checkout -- <root-file>` workarounds that can conflict
- Skipping `--filter=blob:none`: without partial clone the full blob set is fetched even if only a subset of files is written to disk
- Hardcoding the sparse set in the workflow file: the set should be derived from the actual changed packages to stay accurate as the monorepo grows

## Gotchas

- `git status` and `git add -A` only see materialised files; you cannot accidentally stage files outside the sparse set
- Tools that walk the working tree (ESLint, TypeScript project references, pnpm `--recursive`) only find packages that are materialised — verify your affected-package computation includes all transitive dependencies
- `git sparse-checkout reapply` is needed after a `git merge` or `git pull` adds new paths that match your cone patterns
- Cone mode does not support overlapping patterns; each directory is either fully in or fully out
- GitHub's `actions/checkout` action does not enable sparse-checkout by default; use `sparse-checkout` and `sparse-checkout-cone-mode: true` inputs (available since v4.1)

## Verification

```bash
# Confirm cone mode is active
git sparse-checkout list

# Confirm absent directories are truly absent
ls workers/ 2>/dev/null | wc -l   # should match sparse set count

# Confirm blob filter is active (partial clone)
git config core.sparseCheckout        # true
git config remote.origin.partialclonefilter  # blob:none

# Measure working tree size before/after
du -sh .git/objects/
du -sh workers/ packages/
```

## Related

- [monorepo-affected-builds-2026.md](monorepo-affected-builds-2026.md)
- [monorepo-pnpm-turborepo-2026.md](monorepo-pnpm-turborepo-2026.md)
- [git-lfs-partial-clone-alternatives.md](git-lfs-partial-clone-alternatives.md)
- [ci-cd-pipeline-2026.md](ci-cd-pipeline-2026.md)
- [monorepo-ci-parallelization.md](monorepo-ci-parallelization.md)

## Sources

- https://git-scm.com/docs/git-sparse-checkout
- https://github.blog/open-source/git/bring-your-monorepo-down-to-size-with-sparse-checkout/
- https://developers.cloudflare.com/workers/wrangler/
- Turborepo documentation: Filtered tasks
