# github-actions-cache-pnpm-turbo

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Every CI run for example project (example.com) spends 90–120 s re-downloading the pnpm store from the registry even though the lockfile has not changed. Turborepo task hashes change on every run because the remote cache is not configured, so `turbo build` rebuilds every package regardless of whether source files changed. Cache restoration logs show "Cache not found" for every cache key attempted.

## Context

example project is a pnpm monorepo accelerated by Turborepo. Two independent caching layers work together in CI: the **pnpm content-addressable store** (downloaded package tarballs, keyed by lockfile hash) and the **Turborepo task output cache** (built artifacts keyed by input file hash + task definition). When both layers are warm, a CI run with no changed packages completes in under 10 s. Configuring `actions/cache` for pnpm and wiring Turborepo's remote cache to the same Actions cache backend is straightforward but has several ordering and key-strategy pitfalls.

## pnpm store cache with actions/cache

pnpm stores downloaded packages in a content-addressable store whose location is printed by `pnpm store path`. The store is safe to cache across runs because it is immutable: packages are identified by content hash, never overwritten.

```yaml
    - name: Get pnpm store directory
      id: pnpm-cache
      shell: bash
      run: echo "store=$(pnpm store path --silent)" >> $GITHUB_OUTPUT

    - name: Cache pnpm store
      uses: actions/cache@v4
      with:
        path: ${{ steps.pnpm-cache.outputs.store }}
        key: pnpm-store-${{ runner.os }}-${{ hashFiles('**/pnpm-lock.yaml') }}
        restore-keys: |
          pnpm-store-${{ runner.os }}-
```

The `restore-keys` fallback lets a partial restore from a prior lockfile state avoid a full re-download — pnpm fetches only the delta between the cached store and the current lockfile.

Run `pnpm install --frozen-lockfile` **after** the cache step, not before. The cache action restores before `pnpm install` runs; if `install` runs first, the store is empty and packages are fetched before the cache restore even runs.

## Cache key strategies

| Strategy | Key template | Use case |
|---|---|---|
| Lockfile hash | `pnpm-store-{os}-{hash(pnpm-lock.yaml)}` | Standard; re-downloads only on dep changes |
| Lockfile + Node version | `pnpm-store-{os}-{node}-{hash(pnpm-lock.yaml)}` | Matrix CI with multiple Node versions |
| Weekly bucket | `pnpm-store-{os}-{year}-{week}` | Fallback for repos with frequent lockfile churn |
| Composite | key + restore-keys fallback chain | Best of both: exact hit fast-paths, partial hit avoids cold start |

Always scope keys by `runner.os` — a Linux store cannot be restored on macOS and vice versa. On matrix jobs with multiple OS values, the `runner.os` substitution handles this automatically.

## Turborepo remote cache via Actions cache

Turborepo supports pluggable remote cache backends. The `@turborepo/cache-adapter-github` package (or the `--cache-dir` + `actions/cache` manual approach) maps Turborepo's cache to the GitHub Actions cache API without requiring a paid Vercel Remote Cache subscription.

**Option A: Manual `actions/cache` for Turbo outputs**

```yaml
    - name: Cache Turborepo outputs
      uses: actions/cache@v4
      with:
        path: .turbo
        key: turbo-${{ runner.os }}-${{ hashFiles('turbo.json', '**/package.json') }}-${{ github.sha }}
        restore-keys: |
          turbo-${{ runner.os }}-${{ hashFiles('turbo.json', '**/package.json') }}-
          turbo-${{ runner.os }}-

    - name: Build
      run: pnpm turbo build --cache-dir=.turbo
```

**Option B: `TURBO_REMOTE_CACHE_SIGNATURE_KEY` with GitHub-backed cache API**

Turborepo can talk directly to the Actions cache API when `TURBO_API`, `TURBO_TOKEN`, and `TURBO_TEAM` are set to appropriate values. A community adapter implements the Turbo remote cache API contract on top of `@actions/cache`:

```yaml
    - name: Build (with remote cache)
      env:
        TURBO_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        TURBO_API: https://cache.example.com   # self-hosted ducktape-cache or similar
        TURBO_TEAM: example project
      run: pnpm turbo build
```

Option A is simpler and has zero external dependencies. Option B provides shared cache across PRs (different commits can hit the same hash). Choose B only if build times justify the complexity.

## Cache invalidation

| Trigger | pnpm store cache | Turbo output cache |
|---|---|---|
| `pnpm-lock.yaml` changed | Full miss → re-download | Partial miss (task inputs changed) |
| Source file changed | Hit | Task-level miss for affected packages |
| `turbo.json` changed | Hit | Full miss (all task hashes change) |
| `package.json` script changed | Hit | Task miss for that package |
| Runner OS changed | Full miss (key includes OS) | Full miss |
| `actions/cache` eviction (7-day LRU) | Full miss | Full miss |

GitHub Actions cache has a **10 GB per-repo hard limit**. Caches are evicted LRU when the limit is reached. For monorepos with large `.turbo` directories, prune the cache directory or use `--output-logs=errors-only` to reduce what Turborepo writes to disk.

## Post-install cache save ordering

`actions/cache@v4` saves the cache at the end of the job (via a post-step), not when the `uses: actions/cache` line runs. The pnpm store is populated by `pnpm install`, so the save happens after all steps complete. This means:

1. Cache restore → partial or empty store
2. `pnpm install --frozen-lockfile` → fills the store
3. Job steps run
4. Post-step: cache is saved with the new lockfile hash as key

If the job fails after `pnpm install` but before completing, the cache **is still saved** (post-step runs on failure by default with `actions/cache@v4`). Set `save-always: false` to skip saving on failure if you want to avoid caching a corrupted store.

## Anti-patterns

- Running `pnpm install` before the `actions/cache` restore step — wastes the cache entirely.
- Using `github.sha` as the sole cache key without `restore-keys` — every commit is a cache miss (cold start).
- Caching `node_modules` instead of the pnpm store — `node_modules` is OS-specific, contains symlinks, and is invalidated by any package change even in unrelated workspaces.
- Setting a Turbo cache key that includes `github.sha` — Turborepo's own hash function already encodes the input files; adding sha produces guaranteed misses for the same code on reruns.
- Ignoring the 10 GB cache limit — once evictions start, CI randomly misses cache for no apparent reason.

## Gotchas

- `pnpm store path` returns a different value depending on whether `store-dir` is set in `.npmrc` or `pnpmfile.cjs`; always derive the path dynamically with `pnpm store path --silent`.
- `hashFiles('**/pnpm-lock.yaml')` matches ALL lockfiles in submodules and nested packages — this is usually correct for a monorepo but can produce false invalidation if a sub-package lockfile changes independently.
- GitHub Actions cache is branch-scoped for writes: a PR branch can read the base branch cache but writes always go to the PR branch. The base branch's warm cache is available as a restore-keys fallback on first PR run.
- Turborepo `--cache-dir` must point to the same directory used in the `actions/cache` path — a mismatch causes Turbo to write outputs somewhere never saved.
- `TURBO_REMOTE_CACHE_SIGNATURE_KEY` signs cache entries; without it any runner with repo access can read cache artifacts. For open-source repos, consider whether Turbo cache contents are safe to expose.

## Verification

```yaml
    - name: Verify pnpm store populated
      run: |
        COUNT=$(find "$(pnpm store path --silent)" -name '*.tgz' | wc -l)
        echo "Packages in store: $COUNT"
        [ "$COUNT" -gt 0 ] || (echo "Store is empty — cache miss or install failed" && exit 1)

    - name: Verify Turbo cache hit rate
      run: |
        pnpm turbo build --dry=json | jq '.tasks[] | {task: .taskId, cache: .cache.status}'
```

Expected Turbo output on warm cache: all tasks show `"cache": "HIT"`. On first run after key change: `"MISS"`. On partial change: mix of `HIT` and `MISS` only for affected packages.

Check cache sizes in repo Settings → Actions → Caches. If total size approaches 10 GB, add a cleanup step or reduce `--output-logs` verbosity.

## Related

- `github-actions-monorepo-caching.md`
- `github-actions-cache-dependencies.md`
- `github-actions-dependency-locking.md`
- `github-actions-monorepo-affected.md`
- `github-actions-typescript-ci.md`

## Sources

- https://pnpm.io/cli/store
- https://turbo.build/repo/docs/core-concepts/remote-caching
- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows
- https://github.com/actions/cache
- https://turbo.build/repo/docs/reference/command-line-reference/run#--cache-dir
