# pnpm content-addressable store integrity and CI reuse

**Issue:** Persisting an entire installed dependency tree between CI jobs can create stale links, platform mismatches, and hard-to-explain failures.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

pnpm stores package files in a content-addressable store and links them into a project's virtual store before constructing the dependency graph with symlinks. Cache the package store when appropriate, but rebuild the project installation from the committed lockfile rather than treating a restored `node_modules` tree as authoritative.

Use `pnpm install --frozen-lockfile` in CI so dependency resolution cannot silently rewrite the lockfile. Include the operating system, architecture where relevant, pnpm/store compatibility, and lockfile hash in cache identity. Restored cache contents are an optimization; installation must still be correct after a complete miss.

## Operational controls

- Pin the package-manager version through Corepack or an equivalent reviewed mechanism.
- Keep the store on a filesystem that supports pnpm's linking behavior; cross-device layouts may change import behavior.
- Never cache credentials, user configuration containing tokens, or arbitrary workspace output with the store.
- Use `pnpm store prune` as planned maintenance, not during concurrent installs that share a store.
- Measure restore time and hit rate; a large remote cache can be slower than a clean fetch.

## Verification

1. Run a frozen install from an empty store and execute the full build and test suite.
2. Repeat with a restored store and confirm the same lockfile and dependency graph.
3. Change the lockfile and verify the cache key changes.
4. Exercise the runner filesystems and operating systems used in production CI.
5. Confirm a corrupt or unavailable cache falls back to a correct clean installation.

## Sources

- [pnpm: Symlinked node_modules structure](https://pnpm.io/symlinked-node-modules-structure)
- [pnpm CLI: install](https://pnpm.io/cli/install)
- [pnpm CLI: store](https://pnpm.io/cli/store)
