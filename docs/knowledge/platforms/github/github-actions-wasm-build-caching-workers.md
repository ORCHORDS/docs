# GitHub Actions WASM Build Caching for Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A Cloudflare Workers project that bundles a Rust- or AssemblyScript-compiled WASM binary
spends 4–8 minutes on every CI run rebuilding an artifact that rarely changes. Builds are
slow, GitHub Actions minutes are wasted, and developer feedback loops suffer. Caching the
WASM output correctly between workflow runs eliminates the rebuild on unchanged source.

## Context

Cloudflare Workers supports WASM modules imported directly in the bundle. These are compiled
from source languages (most commonly Rust via `wasm-pack`, Go via `tinygo`, or AssemblyScript)
and can take several minutes to compile even on a fast runner. Unlike Node.js `node_modules`,
WASM build outputs depend on the toolchain version, the source files, and `Cargo.lock` /
`package.json` — so the cache key must capture all three. GitHub Actions `actions/cache` can
store and restore these outputs provided the key strategy is stable and the store path is
scoped tightly to only the compiled binary, not intermediate Rust target directories (which
are gigabytes).

## Defining a Tight WASM Cache Key

The cache key must include the toolchain version so a Rust update invalidates the cache
automatically. Hash both the lockfile and every source file under `src/` rather than hashing
the entire repository.

```yaml
# .github/workflows/build.yml
name: Build Workers bundle

on:
  push:
    branches: [main]
  pull_request:

jobs:
  build:
    runs-on: ubuntu-24.04
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Set up Rust toolchain
        uses: dtolnay/rust-toolchain@stable
        with:
          targets: wasm32-unknown-unknown

      - name: Cache wasm-pack binary
        uses: actions/cache@v4
        with:
          path: ~/.cargo/bin/wasm-pack
          key: wasm-pack-${{ runner.os }}-${{ hashFiles('rust-toolchain.toml') }}

      - name: Install wasm-pack if not cached
        run: command -v wasm-pack || cargo install wasm-pack

      - name: Restore WASM build output
        id: wasm-cache
        uses: actions/cache@v4
        with:
          path: wasm/pkg
          key: wasm-${{ runner.os }}-${{ hashFiles('rust-toolchain.toml', 'wasm/Cargo.lock', 'wasm/src/**') }}
          restore-keys: |
            wasm-${{ runner.os }}-

      - name: Build WASM module
        if: steps.wasm-cache.outputs.cache-hit != 'true'
        working-directory: wasm
        run: wasm-pack build --target bundler --release

      - name: Cache pnpm store
        uses: actions/cache@v4
        with:
          path: ~/.pnpm-store
          key: pnpm-${{ runner.os }}-${{ hashFiles('pnpm-lock.yaml') }}

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile
      - run: pnpm run build

      - name: Upload Workers bundle
        uses: actions/upload-artifact@v4
        with:
          name: workers-bundle
          path: dist/
          retention-days: 7
```

## Scoping the Restored Path

Only cache `wasm/pkg` (the compiled output directory), never the Rust `target/` directory.
The `target/` directory for a typical Workers WASM crate exceeds 2 GB and saturates the
5 GB per-repository cache budget within a few runs.

```yaml
      # CORRECT: cache only compiled output
      - uses: actions/cache@v4
        with:
          path: wasm/pkg
          key: wasm-${{ runner.os }}-${{ hashFiles('wasm/Cargo.lock', 'wasm/src/**') }}

      # WRONG: caching the entire target/ directory
      # - uses: actions/cache@v4
      #   with:
      #     path: wasm/target
      #     key: wasm-target-...
```

## Invalidating the Cache on Toolchain Bumps

When `rust-toolchain.toml` changes (pinning a new stable version), the WASM ABI may change.
Include the toolchain file in the hash so old cache entries are never used with a mismatched
compiler. Add a weekly fallback restore key so long-lived PRs still get partial cache benefit.

```yaml
      - uses: actions/cache@v4
        with:
          path: wasm/pkg
          key: >-
            wasm-${{ runner.os }}-
            ${{ hashFiles('rust-toolchain.toml') }}-
            ${{ hashFiles('wasm/Cargo.lock') }}-
            ${{ hashFiles('wasm/src/**') }}
          restore-keys: |
            wasm-${{ runner.os }}-${{ hashFiles('rust-toolchain.toml') }}-
            wasm-${{ runner.os }}-
```

## Anti-patterns

- Caching `wasm/target/` instead of `wasm/pkg/` — bloats the cache store and evicts useful
  caches for other jobs.
- Using a single static key like `wasm-cache` — stale WASM binaries silently ship to
  production when source files change.
- Skipping the `cache-hit` conditional on the build step — doubles CI time on cache hits by
  rebuilding unnecessarily even when `pkg/` is already restored.

## Gotchas

- `hashFiles('wasm/src/**')` requires the glob to be relative to the repository root, not
  the working directory; workflows that `cd` into a subdirectory still need the root-relative
  glob.
- `wasm-pack` writes a `.gitignore` inside `pkg/` that tells git to ignore the directory;
  `actions/cache` respects `.gitignore` unless you explicitly set `enableCrossOsArchive`
  — this is fine on Linux-only runners but causes surprises on cross-OS matrix jobs.

## Verification

```bash
# Confirm the cached pkg directory contains the expected .wasm file
ls -lh wasm/pkg/*.wasm

# Check total size of pkg vs target to validate scope decision
du -sh wasm/pkg wasm/target

# Force a cache miss by touching a source file and re-running the workflow
touch wasm/src/lib.rs
git commit -am "chore: trigger WASM cache miss test"
```

## Related

- `github/github-actions-cache-invalidation-workers-builds.md`
- `github/github-actions-monorepo-caching.md`
- `github/github-actions-d1-snapshot-artifacts.md`

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows
- https://rustwasm.github.io/docs/wasm-pack/commands/build.html
- https://developers.cloudflare.com/workers/languages/rust/
