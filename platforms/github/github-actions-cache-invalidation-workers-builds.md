# Actions Cache Invalidation Strategies for Cloudflare Workers Builds

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Workers CI pipeline takes 3-4 minutes on every PR because `npm install` re-downloads all
packages. After adding `actions/cache` the build drops to 45 seconds — but then a new problem
emerges: stale cache entries return old `wrangler` binaries, outdated Miniflare shims, or
wrong TypeScript declaration files. The cache hit rate is high but the builds are broken.

## Context

Cloudflare Workers builds have several artifact classes that each demand a different invalidation
strategy:

| Artifact class | Cache key driver | Invalidation trigger |
|---|---|---|
| `node_modules` (npm/pnpm) | `package-lock.json` / `pnpm-lock.yaml` hash | Any dep change |
| `wrangler` CLI binary | Wrangler version string | `wrangler` version bump |
| TypeScript build output (`dist/`) | Source hash + `tsconfig.json` hash | Any `.ts` source change |
| Miniflare / `vitest` test environment | Miniflare version + `wrangler.toml` hash | Binding config changes |
| esbuild bundle cache | esbuild version + entry-point hash | Source or config change |

The core problem: GitHub Actions cache keys are immutable. Once a key is written, that exact
key cannot be overwritten. The cache-restore fallback (`restore-keys`) lets you use a stale
cache as a starting point, but stale `wrangler` or Miniflare caches silently break builds.
Explicit key rotation — embedding a version or hash segment that changes when inputs change —
is the correct solution.

## Section 1: Lock-File-Driven Node Modules Cache

This is the foundation. When `pnpm-lock.yaml` changes, the cache key changes and the full
install runs. The `restore-keys` prefix lets the runner use the nearest ancestor cache to
speed up the partial install.

```yaml
# .github/workflows/ci.yml
name: Workers CI

on: [push, pull_request]

env:
  # Increment CACHE_VERSION to force a full cache bust on all branches simultaneously
  # (e.g., when a corrupt cache entry is suspected across the fleet).
  CACHE_VERSION: "v1"

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'   # Built-in pnpm cache; uses pnpm-lock.yaml hash automatically

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      # Manual cache for wrangler binary specifically (wrangler installs a binary at
      # ~/.local/share/wrangler or similar — cache it separately from node_modules)
      - name: Cache wrangler binary
        uses: actions/cache@v4
        with:
          path: ~/.config/.wrangler
          # Key includes the wrangler version extracted from package.json to force
          # invalidation when the wrangler dep version changes.
          key: |
            wrangler-bin-${{ env.CACHE_VERSION }}-${{ runner.os }}-${{ hashFiles('**/package.json') }}
          restore-keys: |
            wrangler-bin-${{ env.CACHE_VERSION }}-${{ runner.os }}-
```

The `CACHE_VERSION` environment variable is a manual escape hatch. When you suspect a corrupt
or inconsistent cache has spread across many branches, bump `CACHE_VERSION` from `v1` to `v2`
in the workflow file. Every existing cache key no longer matches, and all runners rebuild from
scratch on their next run. Old cache entries are evicted automatically after 7 days of non-use.

## Section 2: Composite Key for Workers TypeScript Build Output

Workers projects often compile TypeScript before bundling with esbuild or Wrangler. The
compiled output (`dist/`) can be cached between jobs in the same workflow run using
`actions/cache` with a composite key that spans source files and config.

```yaml
  build-ts:
    runs-on: ubuntu-latest
    outputs:
      dist-cache-key: ${{ steps.ts-key.outputs.key }}
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'
      - run: pnpm install --frozen-lockfile

      - name: Compute TypeScript build cache key
        id: ts-key
        run: |
          # Hash: all .ts source files + tsconfig + wrangler.toml (bindings affect types)
          KEY="ts-dist-${{ env.CACHE_VERSION }}-${{ runner.os }}-$(
            find src -name '*.ts' -o -name '*.tsx' | sort | xargs sha256sum | sha256sum | cut -c1-16
          )-${{ hashFiles('tsconfig.json', 'wrangler.toml') }}"
          echo "key=${KEY}" >> "$GITHUB_OUTPUT"

      - name: Restore TypeScript dist cache
        id: ts-cache
        uses: actions/cache@v4
        with:
          path: dist/
          key: ${{ steps.ts-key.outputs.key }}
          # No restore-keys here: a partial TS cache is worse than no cache
          # because stale .js files mix with new type declarations.

      - name: TypeScript compile
        if: steps.ts-cache.outputs.cache-hit != 'true'
        run: pnpm tsc --noEmit && pnpm build

  deploy-staging:
    needs: build-ts
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'
      - run: pnpm install --frozen-lockfile

      # Restore the same dist cache without `restore-keys` — exact match only.
      - name: Restore TypeScript dist
        uses: actions/cache/restore@v4
        with:
          path: dist/
          key: ${{ needs.build-ts.outputs.dist-cache-key }}
          fail-on-cache-miss: true  # If the build job didn't cache, something is wrong

      - name: Deploy to staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
        run: pnpm wrangler deploy --env staging
```

The critical design here is **no `restore-keys` for the `dist/` cache**. Partial TypeScript
output (where some `.js` files are from the old build and new type files have been added) is
worse than a cold build. Either you get an exact-match cache hit or you build fresh.

## Section 3: Miniflare / Integration Test Environment Cache

Miniflare (the Wrangler local emulator used by `vitest`) downloads KV/D1/R2 emulator binaries
at test startup. These binaries are tied to both the Miniflare version and the `wrangler`
version. Caching them cuts test startup from ~30 seconds to ~2 seconds.

```yaml
  integration-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: 'pnpm'
      - run: pnpm install --frozen-lockfile

      # Miniflare caches workerd binary and KV/D1 emulator blobs.
      # Key must include:
      #   1. wrangler version (workerd version is pinned to wrangler release)
      #   2. wrangler.toml hash (binding additions change which emulators Miniflare initialises)
      #   3. OS (workerd binaries are platform-specific)
      - name: Compute Miniflare cache key
        id: mf-key
        run: |
          WRANGLER_VERSION=$(node -e "console.log(require('./node_modules/wrangler/package.json').version)")
          echo "key=miniflare-${{ env.CACHE_VERSION }}-${{ runner.os }}-${WRANGLER_VERSION}-${{ hashFiles('wrangler.toml', 'wrangler.*.toml') }}" \
            >> "$GITHUB_OUTPUT"

      - name: Cache Miniflare / workerd binaries
        uses: actions/cache@v4
        with:
          path: |
            ~/.cache/miniflare
            node_modules/.cache/miniflare
            # Wrangler stores workerd binary here on Linux
            ~/.local/share/wrangler
          key: ${{ steps.mf-key.outputs.key }}
          restore-keys: |
            miniflare-${{ env.CACHE_VERSION }}-${{ runner.os }}-

      - name: Run integration tests
        env:
          MINIFLARE_EXPERIMENTAL_MUTABLE_WORKERD: "false"
        run: pnpm vitest run --reporter=verbose

      # Force cache save even if tests fail so we don't re-download on retry
      - name: Save Miniflare cache on failure
        if: failure()
        uses: actions/cache/save@v4
        with:
          path: |
            ~/.cache/miniflare
            node_modules/.cache/miniflare
            ~/.local/share/wrangler
          key: ${{ steps.mf-key.outputs.key }}
```

The `restore-keys` fallback on the Miniflare cache is intentional: an old workerd binary will
still run; Miniflare will re-download only the specific emulator blobs that changed. This is
a safe partial-restore scenario, unlike the TypeScript `dist/` case.

## Anti-patterns

- **Caching `node_modules` without `--frozen-lockfile`** — if `npm install` is allowed to
  mutate the lockfile during CI, the cache key (based on the lockfile) never rotates even when
  dependencies actually change. Always use `--frozen-lockfile` (pnpm) or `--ci` (npm).
- **Using `restore-keys` for compiled output** — a partial `dist/` or `.wrangler/` directory
  (files from two different builds mixed together) causes cryptic runtime errors inside the
  Worker. Never use `restore-keys` for build artifacts; only for source-derived caches like
  `node_modules`.
- **Not including `wrangler.toml` in the Miniflare cache key** — adding a D1 binding to
  `wrangler.toml` changes which emulators Miniflare initialises. Without the hash, the old
  cache is reused and the D1 emulator is missing, causing `Cannot read properties of undefined
  (reading 'prepare')` errors.
- **Keeping a corrupt cache entry across PRs** — if a cache was written from a failed build,
  it can propagate to future PRs. The `CACHE_VERSION` env-var bump is the fastest fix. Do
  not try to delete individual cache entries via the UI when you have dozens of branches.
- **Caching the entire `~/.npm` or `~/.pnpm-store` at the workflow level** — the built-in
  `cache: 'pnpm'` in `actions/setup-node` already handles this correctly with the right key.
  A second manual cache covering the same path creates duplicate entries and doubles storage.

## Gotchas

- **GitHub cache storage limit is 10 GB per repository** — Workers projects with many open PRs
  quickly fill this. GitHub evicts entries by last-access time, so active-branch caches survive
  while stale-branch caches are purged. The practical impact: a branch dormant for 7+ days
  will get a cache miss on its next CI run.
- **Cache keys are immutable** — you cannot update a cache entry at the same key. If a build
  partially succeeds and saves a corrupt cache, the next run with the same key (same lockfile
  hash) will restore the corrupt entry. Bump `CACHE_VERSION` or change a key component.
- **`fail-on-cache-miss: true` is available only in `actions/cache/restore@v4`** — the
  combined `actions/cache@v4` step does not support this option. Use the split `restore` / `save`
  actions when you need exact-match enforcement.
- **Miniflare writes to `node_modules/.cache/miniflare` and to home-dir paths** — cache both
  locations or the binary is re-extracted from the npm package on every run even if the npm
  cache is warm.
- **`wrangler deploy` itself is not cacheable** — the `wrangler deploy` step always contacts
  the Cloudflare API and cannot be cached. Do not attempt to cache the Cloudflare upload;
  only cache the local build inputs.

## Verification

```bash
# List cache entries for this repository
gh api repos/{owner}/{repo}/actions/caches \
  --jq '.actions_caches[] | "\(.id) \(.key) \(.size_in_bytes) last_accessed=\(.last_accessed_at)"'

# Delete a specific corrupt cache entry by ID
gh api -X DELETE repos/{owner}/{repo}/actions/caches/{id}

# Delete all caches matching a key prefix (e.g., to force a Miniflare cache bust)
gh api repos/{owner}/{repo}/actions/caches \
  --jq '.actions_caches[] | select(.key | startswith("miniflare-v1")) | .id' |
  xargs -I{} gh api -X DELETE "repos/{owner}/{repo}/actions/caches/{}"

# Verify the Miniflare binary is present in the cache restore
ls -lh ~/.local/share/wrangler/  # Should contain workerd binary

# Check TypeScript dist cache was used (look for "cache-hit: true" in step output)
# In the workflow log, search for "Cache restored from key:"
```

## Related

- `github-actions-cache-dependencies.md` — foundational Actions cache patterns
- `github-actions-cache-pnpm-turbo.md` — Turborepo remote cache with pnpm
- `github-actions-monorepo-caching.md` — per-package cache strategies in monorepos
- `github-actions-cache-safety-for-self-hosted-runners.md` — cache poisoning risks
- `github-actions-cloudflare-deploy-workflow.md` — full deploy workflow this cache feeds into
- `github-actions-matrix-strategy-workers.md` — matrix builds that share cache entries

## Sources

- https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows
- https://github.com/actions/cache
- https://developers.cloudflare.com/workers/wrangler/
- https://miniflare.dev/
- https://docs.github.com/en/rest/actions/cache
