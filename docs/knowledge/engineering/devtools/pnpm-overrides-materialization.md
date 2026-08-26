# pnpm-overrides-materialization

**Issue:** A repo's `package.json` carried a `pnpm.overrides` block pinning vulnerable transitive versions. Everyone assumed the pins were active. They were INERT — never materialized into the lockfile — so the vulnerable versions kept installing. Discovered during the example project audit (2026-08-15): the overrides existed in config but the lockfile still resolved the old deps.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why overrides go inert

1. **Overrides are instructions, not state** — they only take effect when pnpm next resolves and rewrites the lockfile; adding the block without re-locking changes nothing.
2. **`pnpm install` with a satisfied lockfile skips re-resolution** — if the lockfile matches the manifests, pnpm installs from it verbatim, overrides never consulted.
3. **Scope mismatches silently no-op** — an override keyed to a package name that doesn't match the actual dependency path (wrong peer/nested position) applies to nothing.
4. **Mixed registries/workspace layouts** fragment resolution — the override "worked" in one workspace package and not the other.
5. **Nobody verifies the installed tree** — `pnpm why <pkg>` would have shown the vulnerable version still winning; config presence read as enforcement.

## The verification that proves overrides live

1. **`pnpm install` after editing overrides** — force the re-resolution (or delete the lockfile for a full re-resolve in a throwaway branch first).
2. **`pnpm why <vulnerable-pkg>`** — the resolved version must show the override target, in EVERY workspace that pulls it.
3. **Grep the lockfile** for the package entry — the materialized version string must appear under each dependent, not just in the overrides block.
4. **Re-run the audit** (`pnpm audit`) — the finding that motivated the override must clear; if it doesn't, the override isn't live.
5. **Commit the lockfile diff together with the overrides change** — an overrides PR without a lockfile diff is self-evidently inert.

## General rule

1. **Declarative config needs a materialization step** — overrides, resolutions, patch-Packages, and `.npmrc` pins all follow the same law: config ≠ state until the package manager rewrites its lockfile.
2. **The lockfile is the enforcement artifact** — audit the lockfile, not the manifest, when asking "what actually installs".
3. **CI should diff-lockfile-on-manifest-change** — a manifest edit without lockfile movement in the same PR is a red flag by construction.
4. **Security-motivated pins get a verification step in the same PR** — `pnpm why` output pasted next to the override.
5. **Re-check after dependency additions** — new transitive paths can bypass an override that previously covered the whole tree.

## Related

- `../security/` dependency-audit patterns
- `pnpm-workspace-setup.md`
