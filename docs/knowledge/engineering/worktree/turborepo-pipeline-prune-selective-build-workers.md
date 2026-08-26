# Turborepo Pipeline Prune for Selective Workers Builds

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your monorepo hosts twelve Cloudflare Workers and eight shared utility packages. A PR touches only `packages/auth-worker` and `packages/shared-auth`. The full CI run rebuilds and deploys all twelve Workers, wasting fifteen minutes and burning Cloudflare deploy quota. You want Turborepo to prune the task graph to only the affected packages and their transitive dependents, so only `auth-worker` and any Workers that consume `shared-auth` are rebuilt and deployed.

---

## Context

Turborepo's `--filter` flag narrows which packages are included in a pipeline run. Combined with `turbo prune`, which produces a minimal sub-monorepo containing only the packages needed for a given set of targets, you can:

1. Determine which packages changed relative to the base branch.
2. Prune the monorepo to a minimal workspace containing only affected packages and their dependents.
3. Restore from the Turborepo remote cache for packages whose inputs did not change.
4. Run `wrangler deploy` only for Workers whose build output actually changed.

`turbo prune` is primarily designed for Docker layer caching but works equally well for selective CI builds: it outputs a `out/` directory with a trimmed `pnpm-workspace.yaml`, a trimmed root `package.json`, and only the packages that are part of the dependency subgraph.

---

## Determining Affected Packages

```bash
# List packages changed since the merge base of the PR target branch
git fetch origin main --depth=50
BASE=$(git merge-base HEAD origin/main)

# Turborepo's built-in affected detection
pnpm turbo run build --filter="...[${BASE}]" --dry=json \
  | jq -r '.tasks[].package' \
  | sort -u
```

The `...[<ref>]` filter syntax means "all packages that have changed since `<ref>`, plus all packages that depend on them (transitively upward)." This is the key operator for selective builds.

---

## turbo prune: Trimmed Workspace for CI

```bash
# Prune to only packages needed to build and deploy auth-worker
pnpm turbo prune --scope=auth-worker --docker

# Output structure:
# out/
#   json/           <- package.json files only (for dependency install layer)
#   full/           <- full source (for build layer)
#   pnpm-lock.yaml  <- lockfile trimmed to pruned packages
```

In a Docker-based CI workflow you would use `out/json` + `out/pnpm-lock.yaml` as a first layer (install), then `out/full` as the build layer. For non-Docker CI you can use the `out/full/` directory directly as a temporary monorepo root:

```bash
cd out/full
pnpm install --frozen-lockfile
pnpm turbo run build deploy --filter=auth-worker
```

---

## Full GitHub Actions Workflow

```yaml
# .github/workflows/selective-deploy.yml
name: Selective Workers Deploy

on:
  push:
    branches: [main]
  pull_request:

jobs:
  affected:
    runs-on: ubuntu-latest
    outputs:
      matrix: ${{ steps.detect.outputs.matrix }}
      has_changes: ${{ steps.detect.outputs.has_changes }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Detect affected Workers
        id: detect
        run: |
          BASE_REF="${{ github.event.pull_request.base.sha || 'HEAD~1' }}"
          AFFECTED=$(pnpm turbo run build --filter="...[${BASE_REF}]" --dry=json \
            | jq -c '[.tasks[] | select(.package != "//") | .package] | unique')
          echo "matrix={\"package\":${AFFECTED}}" >> "$GITHUB_OUTPUT"
          echo "has_changes=$([ "$AFFECTED" = "[]" ] && echo false || echo true)" >> "$GITHUB_OUTPUT"

  build-and-deploy:
    needs: affected
    if: needs.affected.outputs.has_changes == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix: ${{ fromJson(needs.affected.outputs.matrix) }}
      fail-fast: false
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - name: Prune workspace to ${{ matrix.package }}
        run: |
          pnpm turbo prune --scope="${{ matrix.package }}"
          cp -r out/full /tmp/pruned-workspace
          cd /tmp/pruned-workspace
          pnpm install --frozen-lockfile

      - name: Build ${{ matrix.package }}
        run: |
          cd /tmp/pruned-workspace
          pnpm turbo run build --filter="${{ matrix.package }}"

      - name: Deploy ${{ matrix.package }}
        if: github.ref == 'refs/heads/main'
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          cd /tmp/pruned-workspace
          pnpm turbo run deploy --filter="${{ matrix.package }}"
```

---

## turbo.json Pipeline Definition

```json
{
  "$schema": "https://turbo.build/schema.json",
  "remoteCache": {
    "enabled": true
  },
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "inputs": ["src/**/*.ts", "wrangler.toml", "tsconfig.json", "package.json"],
      "outputs": ["dist/**", ".wrangler/tmp/**"]
    },
    "deploy": {
      "dependsOn": ["build"],
      "cache": false,
      "inputs": ["dist/**", "wrangler.toml"]
    },
    "test": {
      "dependsOn": ["^build"],
      "inputs": ["src/**/*.ts", "test/**/*.ts", "vitest.config.ts"],
      "outputs": ["coverage/**"]
    },
    "check:types": {
      "dependsOn": ["^build"],
      "inputs": ["src/**/*.ts", "tsconfig.json"],
      "outputs": []
    }
  }
}
```

Key decisions:
- `deploy` has `"cache": false` — deployments are side effects and must never be skipped by cache hits.
- `build` declares `outputs` including `.wrangler/tmp/**` so the esbuild artifact is cached between runs.
- `inputs` are explicit: if `wrangler.toml` changes, the build is invalidated even if TypeScript sources did not change.

---

## Selective Prune Script (TypeScript)

For more control than the CLI flags offer, compute the affected set programmatically:

```typescript
// scripts/affected-workers.ts
import { execSync } from "node:child_process";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

interface PnpmPackage {
  name: string;
  path: string;
  private?: boolean;
}

function getChangedFiles(baseRef: string): string[] {
  return execSync(`git diff --name-only ${baseRef}...HEAD`, { encoding: "utf-8" })
    .trim()
    .split("\n")
    .filter(Boolean);
}

function loadPackages(): PnpmPackage[] {
  return JSON.parse(
    execSync("pnpm ls --recursive --json --depth 0", { encoding: "utf-8" })
  );
}

function isWorker(pkg: PnpmPackage): boolean {
  try {
    const tomlPath = join(pkg.path, "wrangler.toml");
    statSync(tomlPath);
    return true;
  } catch {
    return false;
  }
}

function packageOwnsFile(pkg: PnpmPackage, file: string): boolean {
  // normalise to relative paths from repo root
  const repoRoot = execSync("git rev-parse --show-toplevel", { encoding: "utf-8" }).trim();
  const relPkgPath = pkg.path.replace(repoRoot + "/", "");
  return file.startsWith(relPkgPath + "/");
}

const baseRef = process.argv[2] ?? "origin/main";
const changedFiles = getChangedFiles(baseRef);
const packages = loadPackages();

const affectedWorkers = packages
  .filter(isWorker)
  .filter((pkg) => changedFiles.some((f) => packageOwnsFile(pkg, f)));

console.log(JSON.stringify(affectedWorkers.map((p) => p.name)));
```

Usage in CI:

```bash
AFFECTED=$(npx tsx scripts/affected-workers.ts origin/main)
echo "Affected Workers: $AFFECTED"

# Pass to wrangler deploy in a loop
for name in $(echo "$AFFECTED" | jq -r '.[]'); do
  (cd "packages/$name" && wrangler deploy)
done
```

---

## Remote Cache Configuration

Configure Turborepo remote cache to avoid rebuilding identical artifacts across branches:

```bash
# Authenticate once per CI runner (use TURBO_TOKEN + TURBO_TEAM env vars)
export TURBO_TOKEN="${{ secrets.TURBO_REMOTE_CACHE_TOKEN }}"
export TURBO_TEAM="my-org"
export TURBO_REMOTE_CACHE_TIMEOUT=30

# Build — cache hits skip compilation entirely
pnpm turbo run build --filter="[origin/main]"
```

Or self-host the cache backend on Cloudflare Workers + R2 using `turborepo-remote-cache-cloudflare-r2-backend.md`.

---

## Anti-patterns

- **Using `--filter` without `^` or `...` scope modifiers** — `--filter=auth-worker` builds only that package. `--filter=...auth-worker` builds it plus all dependents (upward). `--filter=auth-worker...` builds it plus all its dependencies (downward). For deployment you almost always want `...auth-worker` (upward) to catch packages that consume it.
- **Setting `"cache": true` on deploy tasks** — A cached deploy task will silently skip `wrangler deploy` on subsequent runs, leaving stale Workers in production.
- **Running `turbo prune` in the original workspace** — `turbo prune` writes to `./out/`. If your CI then runs `pnpm install` in the original directory rather than `out/full`, all packages are installed and the prune is wasted.
- **Treating `turbo prune` output as the build artifact** — The pruned workspace is for building, not for shipping. The actual deploy artifact is the output of `wrangler deploy` (a Worker script URL), not the pruned directory.

---

## Gotchas

- `pnpm turbo prune` requires that every package in scope has a `name` field in its `package.json`. Anonymous packages are silently excluded.
- The `--filter="...[ref]"` syntax is evaluated relative to the current `HEAD`. In a detached-HEAD CI checkout, `origin/main` may not resolve. Always run `git fetch origin main` before using ref-based filters.
- Turborepo infers the dependency graph from `package.json` `dependencies` fields, not from TypeScript import statements. A package that imports another without declaring it in `dependencies` will not appear as a dependent in the prune graph — and will be excluded from selective builds when it should have been included.
- `turbo prune --docker` creates two subdirectories (`json/` and `full/`). Without `--docker` it creates only `full/`. The GitHub Actions workflow above uses the non-Docker form.

---

## Verification

```bash
# 1. Confirm the filter matches expected packages
pnpm turbo run build --filter="...[origin/main]" --dry=json \
  | jq '.tasks[] | {pkg: .package, task: .task, cached: .cache.status}'

# 2. Confirm prune output contains exactly the expected packages
pnpm turbo prune --scope=auth-worker
cat out/full/pnpm-workspace.yaml

# 3. Smoke-test the pruned workspace build
cd out/full && pnpm install --frozen-lockfile && pnpm turbo run build

# 4. Verify no unexpected packages are deployed
pnpm turbo run deploy --filter="...[origin/main]" --dry=json \
  | jq '[.tasks[] | select(.task == "deploy") | .package]'
```

---

## Related

- `monorepo-affected-builds-2026.md`
- `monorepo-ci-parallelization.md`
- `turborepo-remote-cache-cloudflare-r2-backend.md`
- `turborepo-task-graph-visualization-debugging.md`
- `monorepo-wrangler-selective-deploy.md`
- `github-actions-matrix-workers-environments.md`

---

## Sources

- [Turborepo Docs — Filtering packages](https://turbo.build/repo/docs/core-concepts/monorepos/filtering)
- [Turborepo Docs — Pruning](https://turbo.build/repo/docs/handbook/deploying-with-docker)
- [Turborepo Docs — Remote caching](https://turbo.build/repo/docs/core-concepts/remote-caching)
- [Cloudflare Workers — wrangler deploy](https://developers.cloudflare.com/workers/wrangler/commands/#deploy)
