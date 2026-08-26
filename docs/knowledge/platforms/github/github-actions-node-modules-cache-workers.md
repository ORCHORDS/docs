# GitHub Actions node_modules Cache for Workers CI

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Workers CI pipeline spends 2–4 minutes on `npm install` every run, even when dependencies haven't changed. You need to cache `node_modules` in GitHub Actions so clean installs only happen when the lockfile changes, keeping CI fast for the common case where only source code has changed.

---

## Context
GitHub Actions provides `actions/cache` to store and restore arbitrary directories between workflow runs. For Node.js projects, caching `node_modules` keyed on the hash of `package-lock.json` ensures the cache is valid exactly as long as dependencies are unchanged. For monorepos, per-package cache keys avoid cache collisions between packages with different dependencies. Using `npm ci --prefer-offline` after a cache hit avoids network calls even for packages already in the npm cache. Cache hit rates above 80% are typical for active projects where most PRs don't touch dependencies.

---

## Setup / Config

```yaml
# .github/workflows/ci.yml — single-package Worker
name: Workers CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          # Built-in npm cache from setup-node (caches ~/.npm, not node_modules)
          # For node_modules caching, use actions/cache below instead
```

---

## Implementation

```yaml
      # Cache node_modules keyed on lockfile hash
      - name: Cache node_modules
        id: cache-node-modules
        uses: actions/cache@v4
        with:
          path: node_modules
          key: node-modules-${{ runner.os }}-${{ hashFiles('package-lock.json') }}
          restore-keys: |
            node-modules-${{ runner.os }}-

      # Install only on cache miss
      - name: Install dependencies
        if: steps.cache-node-modules.outputs.cache-hit != 'true'
        run: npm ci

      # On cache hit, run npm ci --prefer-offline to verify integrity fast
      - name: Verify dependencies (cache hit)
        if: steps.cache-node-modules.outputs.cache-hit == 'true'
        run: npm ci --prefer-offline

      # Report cache status for observability
      - name: Cache hit rate info
        run: |
          echo "Cache hit: ${{ steps.cache-node-modules.outputs.cache-hit }}"

      - name: Typecheck
        run: npx tsc --noEmit

      - name: Test
        run: npx vitest run

      - name: Deploy dry-run
        run: npx wrangler deploy --dry-run
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

```yaml
# .github/workflows/ci-monorepo.yml — monorepo per-package caches
name: Workers Monorepo CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  ci:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        package: [api-worker, auth-worker, storefront-worker]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20

      # Root-level node_modules cache (shared tooling: wrangler, vitest)
      - name: Cache root node_modules
        id: cache-root
        uses: actions/cache@v4
        with:
          path: node_modules
          key: root-node-modules-${{ runner.os }}-${{ hashFiles('package-lock.json') }}
          restore-keys: root-node-modules-${{ runner.os }}-

      - name: Install root dependencies
        if: steps.cache-root.outputs.cache-hit != 'true'
        run: npm ci

      # Per-package node_modules cache
      - name: Cache package node_modules (${{ matrix.package }})
        id: cache-pkg
        uses: actions/cache@v4
        with:
          path: packages/${{ matrix.package }}/node_modules
          key: pkg-node-modules-${{ matrix.package }}-${{ runner.os }}-${{ hashFiles(format('packages/{0}/package-lock.json', matrix.package)) }}
          restore-keys: pkg-node-modules-${{ matrix.package }}-${{ runner.os }}-

      - name: Install package dependencies (${{ matrix.package }})
        if: steps.cache-pkg.outputs.cache-hit != 'true'
        working-directory: packages/${{ matrix.package }}
        run: npm ci

      - name: Test (${{ matrix.package }})
        working-directory: packages/${{ matrix.package }}
        run: npm test

      - name: Deploy dry-run (${{ matrix.package }})
        working-directory: packages/${{ matrix.package }}
        run: npx wrangler deploy --dry-run
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

---

## Integration / Testing

```bash
# View cache usage for your repository (GitHub CLI)
gh api /repos/example-org/example-repo/actions/cache/usage \
  --jq '{ active_caches_size_in_bytes, active_caches_count }'

# List all caches for the repo to inspect keys and sizes
gh api /repos/example-org/example-repo/actions/caches \
  --jq '.actions_caches[] | { key, size_in_bytes, last_accessed_at }'

# Delete a stale cache by ID (forces a clean install on next run)
gh api --method DELETE \
  /repos/example-org/example-repo/actions/caches/{cache_id}

# Locally: verify npm ci --prefer-offline works after a normal install
npm ci
npm ci --prefer-offline   # should complete without network calls

# Measure install time with and without cache locally
time npm ci
time npm ci --prefer-offline
```

---

## Anti-patterns
- **Caching `~/.npm` instead of `node_modules`** — The npm content-addressable cache (`~/.npm`) still runs the full dependency resolution on every run. Caching `node_modules` directly skips both download and resolution.
- **Using `npm install` instead of `npm ci` after cache restore** — `npm install` may silently update packages; `npm ci` is deterministic and respects the lockfile.
- **Single cache key for a monorepo** — A change to one package's lockfile busts the cache for all packages, wasting saved time. Use per-package keys.
- **Not setting `restore-keys`** — Without a fallback prefix, a lockfile change causes a cold start with no partial cache. A prefix like `node-modules-ubuntu-` lets GitHub return the closest older cache.
- **Caching `node_modules` globally across OS types** — Native binaries in `node_modules` are OS-specific. Always include `runner.os` in the cache key.

---

## Gotchas
- GitHub Actions caches expire after 7 days of no access; active repos keep caches alive naturally, but branches with infrequent PRs will see cold starts.
- The total cache storage per repository is 10 GB by default; GitHub evicts the oldest caches when the limit is reached. Monitor with `gh api /repos/{owner}/{repo}/actions/cache/usage`.
- `actions/cache@v4` does not save the cache if the job fails; a failed `npm ci` won't pollute the cache with a broken `node_modules`.
- `npm ci --prefer-offline` still validates `package-lock.json` integrity; it will fail if the lockfile and `node_modules` are out of sync (e.g., someone edited `package-lock.json` manually).
- Cache keys are case-sensitive; `Node-Modules-ubuntu` and `node-modules-ubuntu` are different keys.

---

## Verification

```bash
# After a successful CI run, check that cache was saved
gh run list --workflow ci.yml --limit 5
gh run view <run-id> --log | grep -E 'cache hit|Cache hit|Saved cache'

# Confirm active cache count increased
gh api /repos/example-org/example-repo/actions/cache/usage \
  --jq '.active_caches_count'

# On the next run for the same branch/lockfile, confirm hit
gh run view <next-run-id> --log | grep 'Cache hit: true'
```

---

## Related
- `github-actions-d1-migration-ci.md`
- `github-required-status-checks-workers-ci.md`
- `workers-monorepo-wrangler-config.md`

---

## Sources
- GitHub Actions Cache Documentation — https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows
- actions/cache GitHub Repository — https://github.com/actions/cache
- npm ci Documentation — https://docs.npmjs.com/cli/v10/commands/npm-ci
