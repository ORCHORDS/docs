# CI Cache Optimization for GitHub Actions

**Author:** example.com
**Project:** example project (example.com) — pnpm monorepo, Cloudflare Workers + Pages
**Last updated:** 2026-08-22

---

## Overview

Slow CI pipelines delay feedback, increase cost, and frustrate developers. For example project's pnpm monorepo with Cloudflare Workers and mobile builds, the main sources of latency are package installation, TypeScript compilation, and native mobile build toolchains. Each layer has a caching strategy: pnpm store caching for npm dependencies, Wrangler type caching, Turborepo remote caching via Cloudflare R2 for compiled outputs, and Gradle/Xcode caches for mobile.

This article documents each caching layer with working configuration snippets.

---

## Layer 1: pnpm Store Cache

The pnpm content-addressable store holds every package version downloaded. Caching it means `pnpm install --frozen-lockfile` skips network fetches and only links packages into `node_modules` — typically 10–30 seconds instead of 2–4 minutes.

### Using `actions/setup-node` with built-in pnpm cache

```yaml
# .github/workflows/ci.yml (excerpt)
- uses: pnpm/action-setup@v4
  with:
    version: 9
    # Do NOT set run_install here — handle install separately for control

- uses: actions/setup-node@v4
  with:
    node-version: 22
    cache: pnpm           # tells setup-node to cache ~/.pnpm-store
    # cache-dependency-path defaults to pnpm-lock.yaml at repo root
```

`actions/setup-node` computes the cache key from the content hash of `pnpm-lock.yaml`. When the lockfile changes, the cache misses and a full install runs; otherwise, the cache hit makes install nearly instant.

### Fallback key pattern

For monorepos where different jobs may need different subsets of packages, use a layered key with a restore-keys fallback:

```yaml
- uses: actions/cache@v4
  id: pnpm-cache
  with:
    path: ~/.local/share/pnpm/store
    key: pnpm-${{ runner.os }}-${{ hashFiles('pnpm-lock.yaml') }}
    restore-keys: |
      pnpm-${{ runner.os }}-

- run: pnpm install --frozen-lockfile
```

The restore-key `pnpm-ubuntu-latest-` matches any prior cache with the same OS prefix, so even after a lockfile change the runner reuses most cached packages.

### Verify the store path

pnpm store location varies by OS and install method. Print it in CI to confirm:

```yaml
- run: pnpm store path
```

Typical values:
- Linux (GitHub-hosted): `~/.local/share/pnpm/store`
- macOS (GitHub-hosted): `~/Library/pnpm/store`
- Windows: `%LOCALAPPDATA%\pnpm\store`

Use `$(pnpm store path)` in the cache path to avoid hardcoding.

---

## Layer 2: Wrangler and `.wrangler` Cache

Wrangler caches built Worker scripts and type stubs in `.wrangler/`. Caching this directory avoids redundant builds when neither the Worker source nor its bindings have changed.

```yaml
- uses: actions/cache@v4
  with:
    path: |
      packages/api-worker/.wrangler
      packages/queue-worker/.wrangler
    key: wrangler-${{ runner.os }}-${{ hashFiles('packages/api-worker/wrangler.toml', 'packages/api-worker/src/**') }}
    restore-keys: |
      wrangler-${{ runner.os }}-
```

### `wrangler types` cache

`wrangler types` generates TypeScript types from bindings (KV, D1, R2, etc.). The output in `.wrangler/types/runtime.d.ts` rarely changes unless `wrangler.toml` is modified:

```yaml
- name: Generate Wrangler types (cached)
  run: |
    if [ ! -f packages/api-worker/.wrangler/types/runtime.d.ts ] || \
       [ packages/api-worker/wrangler.toml -nt packages/api-worker/.wrangler/types/runtime.d.ts ]; then
      pnpm --filter api-worker exec wrangler types
    else
      echo "Wrangler types are up to date, skipping generation"
    fi
```

---

## Layer 3: Turborepo Remote Cache with Cloudflare R2

Turborepo caches task outputs (build artifacts, test results) by hashing inputs (source files + dependencies). Locally this lives in `.turbo/`. In CI, a remote cache shared across all runners means a build that passed on one runner is not repeated on another.

Cloudflare R2 is the natural remote cache backend for example project: same account, same access controls, no egress fees.

### Set up the R2 bucket

```bash
# Create a dedicated R2 bucket for Turborepo cache
wrangler r2 bucket create example project-turbo-cache

# Create an R2 API token (read + write, scoped to this bucket)
# Dashboard → R2 → Manage R2 API Tokens → Create API Token
```

### Turborepo remote cache configuration

Turborepo v2+ supports R2 via the S3-compatible API:

```json
// turbo.json
{
  "$schema": "https://turbo.build/schema.json",
  "remoteCache": {
    "enabled": true,
    "signature": true    // HMAC sign cache artifacts
  },
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "package.json", "tsconfig.json", "wrangler.toml"],
      "outputs": ["dist/**", ".wrangler/tmp/**"]
    },
    "typecheck": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "tsconfig.json"],
      "outputs": []
    },
    "lint": {
      "inputs": ["src/**", "eslint.config.js", ".prettierrc.json"],
      "outputs": []
    },
    "test": {
      "dependsOn": ["^build"],
      "inputs": ["src/**", "test/**", "vitest.config.ts"],
      "outputs": ["coverage/**"]
    }
  }
}
```

### GitHub Actions with R2 remote cache

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

env:
  LEFTHOOK: 0
  TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}       # R2 API token secret
  TURBO_REMOTE_CACHE_PROVIDER: s3               # use S3-compatible backend
  TURBO_REMOTE_CACHE_ENDPOINT: https://<ACCOUNT_ID>.r2.cloudflarestorage.com
  TURBO_REMOTE_CACHE_BUCKET: example project-turbo-cache
  TURBO_REMOTE_CACHE_REGION: auto               # R2 requires "auto"
  TURBO_TEAM: example project                              # namespaces the cache

jobs:
  ci:
    name: CI — ${{ matrix.task }}
    runs-on: ubuntu-latest
    strategy:
      matrix:
        task: [build, typecheck, lint, test]

    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Run ${{ matrix.task }} (Turborepo)
        run: pnpm turbo run ${{ matrix.task }} --cache-dir=.turbo

      - name: Upload coverage (test only)
        if: matrix.task == 'test'
        uses: actions/upload-artifact@v4
        with:
          name: coverage
          path: "**/coverage/"
          retention-days: 7
```

### Cache hit rate

Monitor remote cache effectiveness with `--summarize`:

```bash
pnpm turbo run build --summarize
```

Turborepo writes a JSON summary to `.turbo/runs/` showing which tasks hit the cache vs. rebuilt. Aim for > 80% hit rate on PRs. If hit rates are low, check that `inputs` in `turbo.json` does not include auto-generated files that change on every run (e.g., lockfiles, `.wrangler/tmp/`).

---

## Layer 4: Mobile Build Cache

Mobile builds are the longest-running CI steps. iOS (Xcode) and Android (Gradle) both have first-class cache support.

### Android Gradle cache

```yaml
# .github/workflows/mobile-android.yml
jobs:
  android:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          java-version: 17
          distribution: temurin

      - name: Cache Gradle wrapper and caches
        uses: actions/cache@v4
        with:
          path: |
            ~/.gradle/wrapper
            ~/.gradle/caches
            apps/mobile/android/.gradle
          key: gradle-${{ runner.os }}-${{ hashFiles('apps/mobile/android/gradle/wrapper/gradle-wrapper.properties', 'apps/mobile/android/**/*.gradle*') }}
          restore-keys: |
            gradle-${{ runner.os }}-

      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile

      - name: Build Android
        working-directory: apps/mobile
        run: pnpm expo run:android --variant release --no-dev
```

### iOS Xcode derived data cache

```yaml
# .github/workflows/mobile-ios.yml
jobs:
  ios:
    runs-on: macos-15
    steps:
      - uses: actions/checkout@v4

      - name: Cache Xcode DerivedData
        uses: actions/cache@v4
        with:
          path: ~/Library/Developer/Xcode/DerivedData
          key: xcode-${{ runner.os }}-${{ hashFiles('apps/mobile/ios/Podfile.lock', 'apps/mobile/ios/**/*.xcodeproj/project.pbxproj') }}
          restore-keys: |
            xcode-${{ runner.os }}-

      - name: Cache CocoaPods
        uses: actions/cache@v4
        with:
          path: apps/mobile/ios/Pods
          key: pods-${{ runner.os }}-${{ hashFiles('apps/mobile/ios/Podfile.lock') }}
          restore-keys: |
            pods-${{ runner.os }}-

      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile

      - name: Install CocoaPods (if cache miss)
        working-directory: apps/mobile/ios
        run: pod install --repo-update

      - name: Build iOS
        working-directory: apps/mobile
        run: pnpm expo run:ios --configuration Release --no-dev
```

---

## Cache Key Design Principles

1. **Hash the exact inputs that determine the output.** `hashFiles('pnpm-lock.yaml')` covers all npm dependency changes. Adding `src/**` to the key would bust the cache on every code change — wrong for a dependency cache.
2. **Use restore-keys as a fallback.** A partial match is better than a full miss. Restore-keys should be progressively less specific.
3. **Do not cache outputs that rebuild fast.** TypeScript `.js` outputs in `dist/` rebuild in seconds via Turborepo. Caching them in `actions/cache` adds upload/download overhead that exceeds the rebuild time.
4. **Separate cache keys per OS.** Linux and macOS native binaries are not interchangeable; always include `runner.os` in the key.
5. **Set short retention for large caches.** Xcode DerivedData can be multi-gigabyte. Use `retention-days: 7` on artifact uploads; GitHub Actions cache evicts LRU caches automatically at 10 GB per repository.

---

## Measuring Cache Impact

```yaml
- name: Print cache stats
  if: always()
  run: |
    echo "=== pnpm store size ==="
    du -sh $(pnpm store path) 2>/dev/null || echo "store not found"
    echo "=== Turbo cache ==="
    du -sh .turbo 2>/dev/null || echo ".turbo not found"
```

Track wall-clock times in CI by enabling step timing in GitHub Actions (it is on by default in the summary). Compare before/after implementing each cache layer.

---

## Summary

| Layer | Cache key inputs | Savings |
|-------|-----------------|---------|
| pnpm store | `pnpm-lock.yaml` hash | 2–4 min → 10–30 sec |
| Wrangler `.wrangler/` | `wrangler.toml` + `src/**` hash | 30–60 sec on unchanged Workers |
| Turborepo remote (R2) | Per-task input hash | Skips rebuild entirely on cache hit |
| Gradle wrapper + caches | `gradle-wrapper.properties` + `*.gradle` hash | 3–5 min → 30 sec |
| Xcode DerivedData + Pods | `Podfile.lock` + `pbxproj` hash | 10–20 min → 2–3 min |

With all layers in place, a typical PR CI run for example project completes in under 4 minutes instead of 15–20 minutes.

**References**
- Turborepo Remote Caching: https://turbo.build/repo/docs/core-concepts/remote-caching
- Cloudflare R2 S3 compatibility: https://developers.cloudflare.com/r2/api/s3/api
- `actions/cache`: https://github.com/actions/cache
- `actions/setup-node` pnpm cache: https://github.com/actions/setup-node#caching-global-packages-data
