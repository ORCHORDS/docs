# nx-monorepo-setup

**Issue:** Monorepo builds run everything even when only one package changed
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CI takes 30 minutes because all 50 packages rebuild on every PR.

## Pattern / Solution
npx create-nx-workspace. Nx computes affected packages with nx affected --target=build. Caches task results locally and remotely (Nx Cloud). Graph visualization: nx graph. Generators scaffold new libs consistently.

## Gotchas
- Project graph inference may miss custom build steps — configure project.json explicitly
- Nx Cloud remote cache requires account; self-host with nx-remotecache packages

## Related
- turborepo-setup, pnpm-workspace-setup, git-sparse-checkout
