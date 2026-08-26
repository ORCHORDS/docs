# pnpm catalogs version policy

**Issue:** Dependency ranges drift across workspace packages, while an incomplete catalogs rollout can leave direct ranges, stale lockfiles, or literal `catalog:` specifiers in incorrectly published artifacts.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin pnpm and define shared ranges in the default `catalog` or named `catalogs` map in `pnpm-workspace.yaml`. Reference them with `catalog:` or `catalog:<name>`.
- Select `catalogMode` deliberately: `manual` preserves explicit choice, `prefer` uses compatible catalog entries when available, and `strict` rejects additions outside the catalog range.
- Update catalog entries and the lockfile in one reviewed change, then run a frozen-lockfile install in CI.
- Audit direct dependency ranges that should be cataloged and unused entries. Enable `cleanupUnusedCatalogs` only after proving automated removal is acceptable.
- Validate release artifacts with `pnpm pack` or `pnpm publish --dry-run`; pnpm replaces catalog protocol references with concrete ranges during packaging.

## Verification

Test default and named catalogs, missing entries, incompatible ranges, a stale lockfile, each catalog mode, an unused entry, and packed manifests for dependencies, dev/peer/optional dependencies, and overrides. Install the produced tarball with a different package manager.

## Gotchas

- Centralizing a range coordinates edits but does not guarantee one installed version when peer or transitive constraints conflict.
- A catalog bump can affect many packages at once; use affected tests and reviewed lockfile diffs.
- Tools that parse source `package.json` files must understand the catalog protocol or consume packed metadata.

## Official source

- [pnpm catalogs](https://pnpm.io/catalogs)
