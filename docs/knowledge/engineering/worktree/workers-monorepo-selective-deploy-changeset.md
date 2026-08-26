# Selective Worker Deployment in a Monorepo Based on Changed Files

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your monorepo hosts six Cloudflare Workers — `api-gateway`, `auth`, `billing`, `notifications`,
`storage`, and `analytics` — each with its own `wrangler.toml`. A PR that only modifies
`packages/notifications/` should trigger a deployment only for the `notifications` Worker. Full
deployment of all six Workers on every merge wastes time, burns rate limit, and risks unintended
changes to unrelated Workers.

---

## Context

`git diff --name-only` lists files that changed between two refs. By comparing the merge base of
a branch against the branch tip (or against `HEAD` on the default branch), you get the exact set
of changed files. Mapping these paths to Worker package directories lets you determine which
`wrangler.toml` configs are affected.

In GitHub Actions, the CI matrix strategy dynamically expands jobs based on a computed list,
enabling parallel `wrangler deploy` jobs — one per affected Worker — without a static,
hardcoded matrix.

---

## Solution

### 1. Monorepo directory layout

```
repo-root/
  packages/
    api-gateway/
      wrangler.toml
      src/
    auth/
      wrangler.toml
      src/
    billing/
      wrangler.toml
      src/
    notifications/
      wrangler.toml
      src/
    storage/
      wrangler.toml
      src/
    analytics/
      wrangler.toml
      src/
  shared/           # shared library code
    utils/
    types/
```

### 2. Change detection script

```typescript
// scripts/detect-changed-workers.ts
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const PACKAGES_DIR = 'packages';

/**
 * Returns the list of Worker package names whose files changed
 * between BASE_SHA and HEAD_SHA (defaulting to main..HEAD).
 */
function detectChangedWorkers(
  baseSha: string = 'origin/main',
  headSha: string = 'HEAD',
): string[] {
  const diffOutput = execSync(
    `git diff --name-only ${baseSha}...${headSha}`,
    { encoding: 'utf8' },
  ).trim();

  if (!diffOutput) return [];

  const changedFiles = diffOutput.split('\n');

  // Get all Worker packages (directories containing wrangler.toml)
  const allPackages = fs
    .readdirSync(PACKAGES_DIR)
    .filter((pkg) =>
      fs.existsSync(path.join(PACKAGES_DIR, pkg, 'wrangler.toml')),
    );

  const changed = new Set<string>();

  for (const file of changedFiles) {
    // Check if the file belongs to a Worker package
    for (const pkg of allPackages) {
      if (file.startsWith(`${PACKAGES_DIR}/${pkg}/`)) {
        changed.add(pkg);
      }
    }

    // Changes to shared code trigger all Workers
    if (file.startsWith('shared/')) {
      allPackages.forEach((p) => changed.add(p));
      break;
    }
  }

  return [...changed].sort();
}

const [, , baseSha, headSha] = process.argv;
const workers = detectChangedWorkers(baseSha, headSha);

// Output as JSON for GitHub Actions matrix
console.log(JSON.stringify({ worker: workers }));
```

```bash
# Local usage
npx ts-node scripts/detect-changed-workers.ts origin/main HEAD
# {"worker":["billing","notifications"]}
```

### 3. Shell-based detection (CI-friendly fallback)

```bash
#!/usr/bin/env bash
set -euo pipefail

BASE_SHA="${1:-origin/main}"
HEAD_SHA="${2:-HEAD}"
PACKAGES_DIR="packages"

CHANGED_FILES=$(git diff --name-only "${BASE_SHA}...${HEAD_SHA}")
echo "[changeset] changed files:"
echo "$CHANGED_FILES"

CHANGED_WORKERS=()

for pkg_dir in "${PACKAGES_DIR}"/*/; do
  pkg=$(basename "$pkg_dir")
  if [ ! -f "${pkg_dir}wrangler.toml" ]; then continue; fi

  if echo "$CHANGED_FILES" | grep -q "^${PACKAGES_DIR}/${pkg}/"; then
    CHANGED_WORKERS+=("$pkg")
  fi

  # Shared code changes affect all Workers
  if echo "$CHANGED_FILES" | grep -q "^shared/"; then
    CHANGED_WORKERS+=("$pkg")
  fi
done

# Deduplicate
UNIQUE_WORKERS=($(printf '%s\n' "${CHANGED_WORKERS[@]}" | sort -u))

# Emit GitHub Actions matrix JSON
MATRIX=$(printf '%s\n' "${UNIQUE_WORKERS[@]}" | jq -R . | jq -sc '{worker:.}')
echo "matrix=${MATRIX}" >> "$GITHUB_OUTPUT"
echo "[changeset] affected workers: ${MATRIX}"
```

### 4. GitHub Actions workflow

```yaml
# .github/workflows/selective-deploy.yml
name: Selective Worker Deploy

on:
  push:
    branches: [main]

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.changes.outputs.matrix }}
      has-changes: ${{ steps.changes.outputs.has-changes }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history required for git diff

      - name: Detect changed Workers
        id: changes
        run: |
          BASE=$(git merge-base origin/main~1 HEAD)
          CHANGED=$(npx ts-node scripts/detect-changed-workers.ts "$BASE" HEAD)
          echo "matrix=${CHANGED}" >> "$GITHUB_OUTPUT"
          WORKER_COUNT=$(echo "$CHANGED" | jq '.worker | length')
          echo "has-changes=$([ "$WORKER_COUNT" -gt 0 ] && echo true || echo false)" >> "$GITHUB_OUTPUT"

  deploy:
    needs: detect-changes
    if: needs.detect-changes.outputs.has-changes == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.detect-changes.outputs.matrix) }}
      fail-fast: false   # deploy other Workers even if one fails
    steps:
      - uses: actions/checkout@v4

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: packages/${{ matrix.worker }}/package-lock.json

      - name: Install dependencies
        run: npm ci
        working-directory: packages/${{ matrix.worker }}

      - name: Deploy ${{ matrix.worker }}
        run: npx wrangler deploy --config wrangler.toml
        working-directory: packages/${{ matrix.worker }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

      - name: Record deployment
        if: success()
        run: |
          echo "Deployed ${{ matrix.worker }} at $(date -u)" >> deploy-log.txt
```

### 5. Mapping packages to wrangler configs

When a package uses a non-standard config path, maintain a manifest:

```typescript
// scripts/worker-manifest.ts
export interface WorkerManifest {
  package: string;
  wranglerConfig: string;
  sourceDirs: string[];
}

export const WORKER_MANIFEST: WorkerManifest[] = [
  {
    package: 'api-gateway',
    wranglerConfig: 'packages/api-gateway/wrangler.toml',
    sourceDirs: ['packages/api-gateway/src', 'shared/middleware'],
  },
  {
    package: 'auth',
    wranglerConfig: 'packages/auth/wrangler.production.toml',
    sourceDirs: ['packages/auth/src', 'shared/crypto'],
  },
  {
    package: 'notifications',
    wranglerConfig: 'packages/notifications/wrangler.toml',
    sourceDirs: ['packages/notifications/src'],
  },
];
```

---

## Implementation Details

### Handling shared library changes

When `shared/` changes, all Workers must redeploy. The detection script already handles this
case. Alternatively, encode it in the manifest's `sourceDirs` and compute the union:

```typescript
function isAffected(changedFiles: string[], manifest: WorkerManifest): boolean {
  return changedFiles.some((f) =>
    manifest.sourceDirs.some((dir) => f.startsWith(dir + '/')),
  );
}
```

### Skipping unchanged Workers in CI output

The `if: needs.detect-changes.outputs.has-changes == 'true'` guard prevents the deploy job from
running at all when the changed worker list is empty (e.g., a docs-only commit).

### Parallel deploy throughput

With `fail-fast: false` and GitHub's default job concurrency, all affected Workers deploy in
parallel, bounded only by Cloudflare's API rate limits. For monorepos with many Workers, add a
`max-parallel` constraint:

```yaml
strategy:
  matrix: ${{ fromJson(needs.detect-changes.outputs.matrix) }}
  fail-fast: false
  max-parallel: 4
```

---

## Anti-patterns

- **Deploying all Workers on every push.** This is the baseline problem this article solves.
  Even if each deploy takes only 10 seconds, deploying 10 Workers serially adds 100 seconds to
  every CI run regardless of what changed.
- **Using `git diff HEAD~1 HEAD` instead of `git diff <merge-base>...HEAD`.** The `HEAD~1`
  approach misses commits introduced by squash merges and rebases. Always use the three-dot
  (`...`) syntax with the merge base.
- **Hardcoding the worker list in the matrix.** Hardcoded matrices become stale as new Workers
  are added. The detection script derives the matrix from the filesystem.

---

## Gotchas

- `actions/checkout@v4` with default settings performs a shallow clone (`fetch-depth: 1`), which
  makes `git diff origin/main...HEAD` fail because the merge base is not fetched. Always set
  `fetch-depth: 0` for change-detection jobs.
- An empty matrix (`{"worker":[]}`) causes the GitHub Actions matrix expansion to fail. Guard
  with the `has-changes` output and an `if:` condition on the deploy job.
- `wrangler deploy` reads `CLOUDFLARE_ACCOUNT_ID` from the environment or `wrangler.toml`. If
  different Workers belong to different Cloudflare accounts, encode the account ID in each
  package's `wrangler.toml` rather than relying on the environment variable.

---

## Verification

```bash
# Locally simulate what CI will compute
npx ts-node scripts/detect-changed-workers.ts origin/main HEAD

# Dry-run deploy for a specific Worker without publishing
npx wrangler deploy --dry-run --config packages/notifications/wrangler.toml

# Confirm only the expected Workers appear in the CI matrix output
git diff --name-only origin/main...HEAD | head -20
```

---

## Related

- `workers-gitops-auto-deploy-main-branch.md` — full GitOps deploy pipeline
- `workers-bisect-regression-isolation.md` — isolating which commit introduced a regression
- `workers-worktree-parallel-wrangler-dev.md` — parallel dev instances per feature

---

## Sources

- https://git-scm.com/docs/git-diff
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idstrategymatrix
