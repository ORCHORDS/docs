# Monorepo Affected Packages Deploy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Every push to the monorepo triggers a full `wrangler deploy` for all Workers, even when only one package changed.
Selective deployment—re-deploying only Workers affected by a given diff—cuts CI time and reduces accidental production churn.

## Context
A pnpm monorepo hosts multiple Cloudflare Workers alongside shared libraries.
When `lib-auth` changes, only the Workers that import it need to be redeployed; unrelated Workers should be skipped.
Turborepo's `--filter` flag combined with `pnpm` dependency graphs and `git diff` provides the tooling to compute the affected set and drive selective `wrangler deploy` calls.

---

## Setup — Package Dependency Graph

Each Worker's `package.json` declares its library dependencies explicitly using `workspace:*`:

```json
// packages/api-worker/package.json
{
  "name": "@example-org/example-repo",
  "private": true,
  "dependencies": {
    "@example-org/example-repo": "workspace:*",
    "@example-org/example-repo": "workspace:*"
  },
  "scripts": {
    "deploy": "wrangler deploy",
    "deploy:staging": "wrangler deploy --env staging"
  }
}
```

```json
// packages/auth-worker/package.json
{
  "name": "@example-org/example-repo",
  "private": true,
  "dependencies": {
    "@example-org/example-repo": "workspace:*"
  },
  "scripts": {
    "deploy": "wrangler deploy",
    "deploy:staging": "wrangler deploy --env staging"
  }
}
```

```json
// packages/queue-consumer/package.json
{
  "name": "@example-org/example-repo",
  "private": true,
  "dependencies": {
    "@example-org/example-repo": "workspace:*"
  },
  "scripts": {
    "deploy": "wrangler deploy"
  }
}
```

---

## Section 1 — Compute Affected Packages from Git Diff

Use `pnpm` and `turbo` to resolve the transitive affected set for a given diff:

```typescript
// scripts/affected-workers.ts
import { execSync } from 'node:child_process';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

interface PackageJson {
  name: string;
  private?: boolean;
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
  scripts?: Record<string, string>;
}

const ROOT = resolve(__dirname, '..');

function readPackageJson(dir: string): PackageJson {
  return JSON.parse(readFileSync(resolve(dir, 'package.json'), 'utf8'));
}

function getChangedFiles(base: string): string[] {
  return execSync(`git diff --name-only ${base}...HEAD`, { encoding: 'utf8' })
    .split('\n')
    .filter(Boolean);
}

function getPackageDir(pkgName: string): string | null {
  const dirs = readdirSync(resolve(ROOT, 'packages'), { withFileTypes: true })
    .filter(e => e.isDirectory())
    .map(e => resolve(ROOT, 'packages', e.name));
  for (const dir of dirs) {
    try {
      const pkg = readPackageJson(dir);
      if (pkg.name === pkgName) return dir;
    } catch { /* ignore */ }
  }
  return null;
}

function getWorkers(): Array<{ dir: string; pkg: PackageJson }> {
  return readdirSync(resolve(ROOT, 'packages'), { withFileTypes: true })
    .filter(e => e.isDirectory())
    .flatMap(e => {
      const dir = resolve(ROOT, 'packages', e.name);
      try {
        const pkg = readPackageJson(dir);
        // Workers have a wrangler.toml and are private
        const hasWrangler = (() => {
          try {
            readFileSync(resolve(dir, 'wrangler.toml'));
            return true;
          } catch { return false; }
        })();
        return hasWrangler ? [{ dir, pkg }] : [];
      } catch { return []; }
    });
}

function isWorkerAffected(
  worker: { dir: string; pkg: PackageJson },
  changedFiles: string[],
): boolean {
  // Direct file change in the worker package itself
  const relDir = worker.dir.replace(ROOT + '/', '');
  if (changedFiles.some(f => f.startsWith(relDir + '/'))) return true;

  // Transitive: a workspace dependency changed
  const deps = {
    ...worker.pkg.dependencies,
    ...worker.pkg.devDependencies,
  };
  for (const [depName] of Object.entries(deps)) {
    if (!depName.startsWith('@orchords/')) continue;
    const depDir = getPackageDir(depName);
    if (!depDir) continue;
    const depRelDir = depDir.replace(ROOT + '/', '');
    if (changedFiles.some(f => f.startsWith(depRelDir + '/'))) return true;
  }
  return false;
}

const base = process.argv[2] ?? 'origin/main';
const changedFiles = getChangedFiles(base);
console.error(`Changed files vs ${base}:`);
changedFiles.forEach(f => console.error(` - ${f}`));

const workers = getWorkers();
const affected = workers.filter(w => isWorkerAffected(w, changedFiles));

// Output package names, one per line, for use in CI matrix
affected.forEach(w => console.log(w.pkg.name));
```

---

## Section 2 — Turborepo Filter-Based Selective Deploy

Turborepo's `--filter` flag natively understands the dependency graph.
Use it as an alternative to the custom script when your pipeline is already Turborepo-based:

```json
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "deploy": {
      "dependsOn": ["^build"],
      "cache": false,
      "env": ["CLOUDFLARE_API_TOKEN"]
    },
    "deploy:staging": {
      "dependsOn": ["^build"],
      "cache": false,
      "env": ["CLOUDFLARE_API_TOKEN"]
    },
    "build": {
      "outputs": ["dist/**"]
    }
  }
}
```

```bash
# Deploy only packages affected since origin/main (including transitive deps)
npx turbo deploy --filter='...[origin/main]' --concurrency=2

# Staging deploy for affected packages only
npx turbo deploy:staging --filter='...[origin/main]'
```

The `...[origin/main]` syntax tells Turborepo: "all packages that have changed relative to `origin/main`, plus any packages that depend on them."

---

## Section 3 — GitHub Actions Matrix from Affected Set

```yaml
# .github/workflows/selective-deploy.yml
name: Selective Workers Deploy

on:
  push:
    branches: [main]

jobs:
  compute-affected:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.affected.outputs.matrix }}
      has_workers: ${{ steps.affected.outputs.has_workers }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # need full history for git diff

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Compute affected Workers
        id: affected
        run: |
          # Get affected worker package names
          AFFECTED=$(npx tsx scripts/affected-workers.ts origin/main~1)
          echo "Affected workers:"
          echo "$AFFECTED"

          if [ -z "$AFFECTED" ]; then
            echo "has_workers=false" >> "$GITHUB_OUTPUT"
            echo 'matrix={"include":[]}' >> "$GITHUB_OUTPUT"
          else
            # Build JSON matrix
            MATRIX=$(echo "$AFFECTED" | jq -Rsc '
              split("\n") |
              map(select(length > 0)) |
              {"include": map({"package": .})}
            ')
            echo "matrix=$MATRIX" >> "$GITHUB_OUTPUT"
            echo "has_workers=true" >> "$GITHUB_OUTPUT"
          fi

  deploy:
    needs: compute-affected
    if: needs.compute-affected.outputs.has_workers == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.compute-affected.outputs.matrix) }}
      max-parallel: 2
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Deploy ${{ matrix.package }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          PKG_DIR=$(pnpm -r exec sh -c 'echo "$PWD"' --filter "${{ matrix.package }}")
          cd "$PKG_DIR"
          npx wrangler deploy
```

---

## Anti-patterns

- Always deploying all Workers on every push to `main` — increases blast radius and deploy time proportional to monorepo growth
- Using `git diff HEAD~1` instead of `git diff origin/main...HEAD` — misses multi-commit PRs and produces false negatives on merge commits
- Skipping transitive dependency resolution — a change to `lib-auth` won't trigger `api-worker` if only the direct file diff is checked
- Setting `max-parallel` to the number of Workers without considering Cloudflare API rate limits — rapid concurrent deploys can hit the Workers deploy rate limit

## Gotchas

- Turborepo's `[origin/main]` filter requires `fetch-depth: 0` in `actions/checkout`; a shallow clone will error with "couldn't find base ref"
- `pnpm -r exec` emits output from all packages concurrently; pipe through `--filter` to scope it
- `wrangler deploy` always deploys the *current* build artifact — ensure `pnpm build` (or `turbo build`) runs before `wrangler deploy` in the same job, or the stale `dist/` from a previous commit ships
- When a shared config file like `wrangler.toml` at the repo root changes, all Workers are affected — include root-level path globs in the affected computation

## Verification

```bash
# Dry-run the affected-workers script against the last merge
npx tsx scripts/affected-workers.ts HEAD~1

# Confirm turbo filter produces the expected set
npx turbo deploy --filter='...[HEAD~1]' --dry-run=json | jq '.tasks[].taskId'

# Check which packages turbo considers affected
npx turbo run build --filter='...[origin/main]' --dry-run
```

## Related

- `monorepo-affected-builds-2026.md`
- `monorepo-wrangler-selective-deploy.md`
- `turborepo-pipeline-prune-selective-build-workers.md`
- `monorepo-ci-parallelization.md`
- `github-actions-matrix-workers-environments.md`
- `monorepo-deploy-order-workers-service-bindings.md`

## Sources

- https://turbo.build/repo/docs/reference/run#--filter-string
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://pnpm.io/filtering
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow
