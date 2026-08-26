# Affected Package Detection in Monorepo: Matrix Deploy Only Changed Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A monorepo holds 10+ Cloudflare Workers. Every push to `main` re-deploys all of them, wasting 8–12 minutes of CI time and risking unintended side-effects from deploying Workers that have no actual changes. You need to detect which packages changed relative to the base branch and deploy only those.

## Context

The strategy: use `git diff --name-only` against the merge base to get changed file paths, map each path to its owning Worker via a lookup table, then feed the result into a GitHub Actions matrix so only affected Workers are deployed in parallel. Works for both PRs (diff against base branch) and pushes to `main` (diff against the previous SHA).

---

## Section 1: Monorepo Layout

```
repo-root/
├── workers/
│   ├── api-gateway/
│   │   ├── src/
│   │   ├── wrangler.toml
│   │   └── package.json
│   ├── auth-service/
│   │   ├── src/
│   │   ├── wrangler.toml
│   │   └── package.json
│   ├── image-resizer/
│   │   ├── src/
│   │   ├── wrangler.toml
│   │   └── package.json
│   └── webhook-handler/
│       ├── src/
│       ├── wrangler.toml
│       └── package.json
├── packages/
│   ├── shared-utils/       # shared library — change triggers ALL workers
│   └── db-client/
├── scripts/
│   └── affected-workers.ts
└── package.json
```

## Section 2: Affected Workers Detection Script

```typescript
// scripts/affected-workers.ts
// Usage: npx tsx scripts/affected-workers.ts <base-sha> <head-sha>
// Outputs: JSON array of worker names that need re-deployment

import { execSync } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';

const REPO_ROOT = new URL('..', import.meta.url).pathname;
const WORKERS_DIR = join(REPO_ROOT, 'workers');
const SHARED_PACKAGES_DIR = join(REPO_ROOT, 'packages');

/** Files matching these patterns force a full re-deploy of every Worker. */
const GLOBAL_TRIGGERS = [
  /^package\.json$/,
  /^package-lock\.json$/,
  /^\.github\/workflows\//,
  /^packages\//,           // any shared package change
];

function getChangedFiles(baseSha: string, headSha: string): string[] {
  const out = execSync(
    `git diff --name-only ${baseSha}...${headSha}`,
    { cwd: REPO_ROOT, encoding: 'utf8' }
  );
  return out.trim().split('\n').filter(Boolean);
}

function listWorkers(): string[] {
  if (!existsSync(WORKERS_DIR)) return [];
  return readdirSync(WORKERS_DIR, { withFileTypes: true })
    .filter(d => d.isDirectory() && existsSync(join(WORKERS_DIR, d.name, 'wrangler.toml')))
    .map(d => d.name);
}

function determineAffected(changedFiles: string[], allWorkers: string[]): string[] {
  // Check if any changed file triggers a global re-deploy
  const forceAll = changedFiles.some(f =>
    GLOBAL_TRIGGERS.some(pattern => pattern.test(f))
  );
  if (forceAll) {
    console.error('[affected] Global trigger detected — deploying ALL workers');
    return allWorkers;
  }

  const affected = new Set<string>();
  for (const file of changedFiles) {
    // Check if the file belongs to a Worker directory
    if (file.startsWith('workers/')) {
      const parts = file.split('/');
      const workerName = parts[1];
      if (workerName && allWorkers.includes(workerName)) {
        affected.add(workerName);
      }
    }
  }

  return [...affected];
}

function main() {
  const [baseSha, headSha] = process.argv.slice(2);
  if (!baseSha || !headSha) {
    console.error('Usage: affected-workers.ts <base-sha> <head-sha>');
    process.exit(1);
  }

  const changed = getChangedFiles(baseSha, headSha);
  console.error(`[affected] Changed files (${changed.length}):`, changed);

  const allWorkers = listWorkers();
  console.error(`[affected] All workers:`, allWorkers);

  const affected = determineAffected(changed, allWorkers);
  console.error(`[affected] Deploying:`, affected);

  // Output valid JSON to stdout for GitHub Actions
  console.log(JSON.stringify(affected));
}

main();
```

## Section 3: GitHub Actions Workflow

```yaml
# .github/workflows/deploy-monorepo.yml
name: Deploy Affected Workers

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
  CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

jobs:
  detect:
    name: Detect Affected Workers
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.set-matrix.outputs.matrix }}
      has_changes: ${{ steps.set-matrix.outputs.has_changes }}

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # required for git diff across commits

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      - name: Determine base and head SHAs
        id: shas
        run: |
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            echo "base=${{ github.event.pull_request.base.sha }}" >> "$GITHUB_OUTPUT"
            echo "head=${{ github.event.pull_request.head.sha }}" >> "$GITHUB_OUTPUT"
          else
            # Push to main: diff against previous commit
            echo "base=${{ github.event.before }}" >> "$GITHUB_OUTPUT"
            echo "head=${{ github.sha }}" >> "$GITHUB_OUTPUT"
          fi

      - name: Compute affected workers
        id: set-matrix
        run: |
          BASE="${{ steps.shas.outputs.base }}"
          HEAD="${{ steps.shas.outputs.head }}"

          # Handle the case where base is all-zeros (first push to branch)
          if [ "$BASE" = "0000000000000000000000000000000000000000" ]; then
            BASE=$(git rev-list --max-parents=0 HEAD)
          fi

          AFFECTED=$(npx tsx scripts/affected-workers.ts "$BASE" "$HEAD")
          echo "Affected workers JSON: $AFFECTED"

          if [ "$AFFECTED" = "[]" ]; then
            echo "has_changes=false" >> "$GITHUB_OUTPUT"
            echo "matrix={\"worker\":[]}" >> "$GITHUB_OUTPUT"
          else
            echo "has_changes=true" >> "$GITHUB_OUTPUT"
            echo "matrix={\"worker\":$AFFECTED}" >> "$GITHUB_OUTPUT"
          fi

  deploy:
    name: Deploy ${{ matrix.worker }}
    runs-on: ubuntu-latest
    needs: detect
    if: needs.detect.outputs.has_changes == 'true'
    strategy:
      matrix: ${{ fromJson(needs.detect.outputs.matrix) }}
      fail-fast: false   # deploy remaining workers even if one fails

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm

      - run: npm ci

      - name: Install worker dependencies
        working-directory: workers/${{ matrix.worker }}
        run: npm ci

      - name: Deploy ${{ matrix.worker }}
        working-directory: workers/${{ matrix.worker }}
        run: |
          echo "Deploying worker: ${{ matrix.worker }}"
          npx wrangler deploy --env production

      - name: Health check
        working-directory: workers/${{ matrix.worker }}
        run: |
          WORKER_URL=$(npx wrangler deployments list --env production 2>/dev/null \
            | grep 'https://' | head -1 | awk '{print $1}' || echo "")
          if [ -n "$WORKER_URL" ]; then
            ../../scripts/health-check.sh "$WORKER_URL" 8 5
          else
            echo "::warning::Could not determine Worker URL for health check"
          fi
```

## Section 4: Mapping Shared Package Changes

```typescript
// scripts/package-worker-map.ts
// Explicit mapping: shared package → Workers that depend on it
// Used when package.json dependency tracking is needed

export const PACKAGE_WORKER_MAP: Record<string, string[]> = {
  'packages/shared-utils': ['api-gateway', 'auth-service', 'webhook-handler'],
  'packages/db-client': ['api-gateway', 'auth-service'],
};

export function workersForPackage(changedPackagePath: string): string[] {
  for (const [pkg, workers] of Object.entries(PACKAGE_WORKER_MAP)) {
    if (changedPackagePath.startsWith(pkg + '/')) {
      return workers;
    }
  }
  return [];
}
```

## Anti-patterns

- **`fetch-depth: 1` (shallow clone)**: `git diff` needs full history. Always set `fetch-depth: 0` in `actions/checkout`.
- **Diffing against `HEAD~1`**: On merge commits this misses the range of squashed changes. Use `base...head` triple-dot syntax.
- **Deploying in sequence in a matrix**: Use `fail-fast: false` so one broken Worker does not block others from deploying.
- **Ignoring `package.json` changes at the root**: A new workspace dep or engine change should invalidate all Workers.

## Gotchas

- `github.event.before` is `0000000000000000000000000000000000000000` on the first push to a new branch. Guard against this or fall back to the initial commit.
- The `matrix` output must be a valid JSON string. Wrap `fromJson()` carefully; an empty array `[]` causes the matrix job to be skipped, not errored.
- Workers with symlinked `node_modules` from a hoisted workspace root may need `npm ci` run at the repo root, not inside the Worker directory.

## Verification

```bash
# Simulate: only api-gateway changed
git stash
touch workers/api-gateway/src/dummy.ts && git add -A && git commit -m 'test'
npx tsx scripts/affected-workers.ts HEAD~1 HEAD
# Expected: ["api-gateway"]

# Simulate: shared package changed
touch packages/shared-utils/index.ts && git add -A && git commit -m 'test2'
npx tsx scripts/affected-workers.ts HEAD~1 HEAD
# Expected: ["api-gateway","auth-service","webhook-handler"]
```

## Related

- `documentation/categories/github/github-actions-workers-post-deploy-health-check.md`
- `documentation/workers/workers-wrangler-toml-environments.md`

## Sources

- https://git-scm.com/docs/git-diff
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/using-jobs-in-a-workflow#using-a-matrix-for-your-jobs
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
