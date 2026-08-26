# GitHub Actions Cache for Wrangler Build Optimization

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Cloudflare Workers deployments for example project / example.com were taking 4–6 minutes per job in CI — most of that time was `pnpm install` re-downloading the entire dependency graph on every run. The Workers bundle step (`esbuild` via Wrangler) was also re-compiling unchanged TypeScript on every push to feature branches. Caching the pnpm store, the TypeScript incremental build output, and the Wrangler bundle hash reduces cold-path deploys to under 90 seconds.

## Context

GitHub Actions provides the `actions/cache` action backed by a blob store keyed by a cache key string and a list of restore-keys. Caches are scoped to a branch; the default branch (`main`) cache is readable by all branches, so feature branches can always warm-hit the base dependency cache. Wrangler's own caching surfaces two hot paths: the npm package store (pnpm content-addressable store) and the TypeScript compiler's `.tsbuildinfo` incremental output.

## Caching the pnpm Store

The pnpm store lives outside the project directory at `~/.pnpm-store` by default. `actions/setup-node` does not cache it; use `pnpm/action-setup` with its built-in `cache` option or add a manual `actions/cache` step.

```yaml
# .github/workflows/deploy-worker.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "pnpm"           # built-in pnpm store caching

      - name: Install dependencies
        run: pnpm install --frozen-lockfile
```

The `cache: "pnpm"` shorthand uses `pnpm store path` to locate the store and builds the cache key from `pnpm-lock.yaml`. No additional `actions/cache` step is needed for dependencies.

## Caching TypeScript Incremental Build Output

Wrangler invokes `esbuild` for bundling but many projects run `tsc --build` first to emit type-checked JavaScript that Wrangler then bundles. The `.tsbuildinfo` file makes subsequent TypeScript compilations incremental.

```yaml
      - name: Restore TypeScript build cache
        uses: actions/cache@v4
        with:
          path: |
            apps/feed/dist
            apps/feed/.tsbuildinfo
          key: tsc-${{ runner.os }}-${{ hashFiles('apps/feed/src/**/*.ts', 'apps/feed/tsconfig.json') }}
          restore-keys: |
            tsc-${{ runner.os }}-

      - name: Build TypeScript
        working-directory: apps/feed
        run: pnpm tsc --build

      - name: Deploy with Wrangler
        working-directory: apps/feed
        run: pnpm wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

The cache key includes a hash of all `.ts` source files and `tsconfig.json`. On a cache miss, the full compile runs; on a hit, only changed files are recompiled.

## Caching Wrangler's Module Resolution Output

Wrangler itself caches resolved npm module entries in a `.wrangler/tmp` directory. This cache is machine-local and rarely persisted in CI. Adding it to the Actions cache prevents redundant resolution on repeat deploys of the same lockfile.

```yaml
      - name: Restore Wrangler build cache
        uses: actions/cache@v4
        id: wrangler-cache
        with:
          path: |
            .wrangler/tmp
            apps/feed/.wrangler/tmp
          key: wrangler-${{ runner.os }}-${{ hashFiles('**/pnpm-lock.yaml', 'apps/feed/wrangler.toml') }}
          restore-keys: |
            wrangler-${{ runner.os }}-
```

## Cache Key Strategy for Multi-Worker Monorepos

Each Worker app needs an independently keyed cache to avoid one app's build artifacts polluting another's cache. Use the `working_directory` input (from the reusable workflow pattern) in the cache key:

```yaml
      - name: Restore per-worker build cache
        uses: actions/cache@v4
        with:
          path: ${{ inputs.working_directory }}/dist
          key: worker-build-${{ inputs.worker_name }}-${{ runner.os }}-${{ hashFiles(format('{0}/src/**', inputs.working_directory), format('{0}/wrangler.toml', inputs.working_directory)) }}
          restore-keys: |
            worker-build-${{ inputs.worker_name }}-${{ runner.os }}-
```

The restore-key prefix (`worker-build-example project-feed-ubuntu-latest-`) ensures the cache falls back to the previous run's artifacts for the same worker even when source hashes change, enabling incremental builds on every push.

## Full Optimised Workflow

```yaml
name: Deploy Feed Worker (Optimised)

on:
  push:
    branches: [main]
    paths: ["apps/feed/**"]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "pnpm"

      - uses: actions/cache@v4
        with:
          path: |
            apps/feed/dist
            apps/feed/.tsbuildinfo
            apps/feed/.wrangler/tmp
          key: feed-build-${{ runner.os }}-${{ hashFiles('apps/feed/src/**/*.ts', 'apps/feed/wrangler.toml', 'pnpm-lock.yaml') }}
          restore-keys: |
            feed-build-${{ runner.os }}-

      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter @example project/feed build
      - name: Deploy
        run: pnpm --filter @example project/feed wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

## Anti-patterns

- Caching `node_modules` directly instead of the pnpm content-addressable store — the store de-duplicates hard-links across projects; caching `node_modules` caches duplicates and is slower to restore.
- Using a single flat cache key for all Workers in a monorepo; a change to one Worker's `tsconfig.json` busts all others' caches.
- Caching `.wrangler/tmp` without including `wrangler.toml` in the key — a `wrangler.toml` change (e.g., new binding) does not change source files but does invalidate the Wrangler module resolution cache.
- Restoring a stale TypeScript incremental cache when `tsconfig.json` changes `strict` or `target` settings — always include `tsconfig.json` in the hash.
- Not using `restore-keys` — without fallback keys, every PR where a single file changed causes a full cold-path build.

## Gotchas

- GitHub Actions cache has a 10 GB limit per repository. A monorepo with many Workers can exhaust this; use `actions/cache` with `enableCrossOsArchive: false` and monitor usage in the "Caches" tab under Actions settings.
- Caches created by pull request workflows cannot be accessed by the `main` branch workflow (the reverse is allowed). Push-triggered deploys on `main` will only hit caches created by previous `main` runs.
- The `pnpm/action-setup` `cache` option is incompatible with a manual `actions/cache` step targeting the same pnpm store path — use one or the other.
- Wrangler v3+ changed `.wrangler/tmp` behaviour; verify the tmp path exists after a `wrangler deploy --dry-run` before adding it to the cache path list.
- Saving a cache on a failed workflow run is disabled by default; use `cache-on-failure: true` if incremental test output should survive a flaky test failure.

## Verification

1. Check the "Cache" section in the Actions run summary; confirm "Cache Hit" for the pnpm store on a second run with no lockfile changes.
2. Measure total job duration across three consecutive pushes; the second and third should show a >60% reduction vs. the first.
3. Change a single `.ts` file and confirm the TypeScript incremental cache restores and only recompiles the changed file (inspect `tsc` output for "N files unchanged").
4. Run `gh cache list --repo example project-app/backend` to inspect cache sizes and eviction dates.

## Related

- `github-actions-cache-dependencies.md`
- `github-actions-cache-invalidation-workers-builds.md`
- `github-actions-cache-segmentation-workers-environment.md`
- `github-actions-monorepo-caching.md`
- `github-actions-reusable-workflows-workers-deploy.md`

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://pnpm.io/cli/store
- https://www.typescriptlang.org/docs/handbook/project-references.html
