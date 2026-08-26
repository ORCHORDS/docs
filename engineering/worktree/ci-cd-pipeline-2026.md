# ci-cd-pipeline-2026

**Issue:** A team has a CI pipeline that takes 45 minutes. The team debates caching, parallelism, test selection. The team needs the 2026 reference for CI/CD pipeline design.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 pipeline stages

1. **Lint + type check** (1-2 min). Fast, parallel.
2. **Unit tests** (2-10 min). Parallel, sharded.
3. **Build** (3-15 min). Cached.
4. **Integration / E2E tests** (10-30 min). Parallel, sharded, isolated DBs.
5. **Deploy** (5-15 min). Stage-gated, manual approval for production.

## The 5 caching strategies

1. **Dependency cache** (`actions/cache`, `--cache-from` in Docker). Restore before install.
2. **Build cache** (Turborepo, Nx, Bazel remote cache). Keyed by content hash.
3. **Test cache** (jest, vitest with `--cache`). Skips unchanged tests.
4. **Docker layer cache** (BuildKit, Buildx). Reuses unchanged layers.
5. **Browser binary cache** (Playwright, Cypress). Restores installed browsers.

## The 5 parallelism strategies

1. **Sharding by file count** (Jest `--shard`, pytest-xdist). 4-16 shards typical.
2. **Sharding by directory** (Nx affected, Turborepo filter). Only build/test affected.
3. **Matrix builds** (GitHub Actions matrix, GitLab parallel). Multiple OS/Node versions.
4. **Service containers** for integration tests (postgres, redis as sidecars).
5. **Self-hosted runners** for speed (GitHub Actions runners, CircleCI runners).

## The 5 anti-patterns

1. **Single sequential pipeline** for 1000 tests. 45+ minutes wasted.
2. **No cache strategy.** Reinstalls dependencies every run.
3. **`npm install` in CI without lockfile verification.** Drift between dev and CI.
4. **Running all tests on every PR.** Use affected-only.
5. **No flaky test detection.** Same test fails 5% of the time; ignored by team.

## Source URLs (verified 2026-08-10)

- https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows
- https://turbo.build/repo/docs/core-concepts/caching
- https://nx.dev/ci/features/remote-cache
- https://jestjs.io/docs/sharding
- https://playwright.dev/docs/ci
