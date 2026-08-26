# pnpm-workspace-setup

**Issue:** npm workspaces slow, disk inefficient for monorepo
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
npm install in monorepo duplicates packages across workspace packages; slow cold installs.

## Pattern / Solution
Install pnpm. Create pnpm-workspace.yaml listing packages glob. pnpm install at root installs all workspaces. Hard-links deduplicate packages in global store. Use pnpm -r run build to run scripts across all packages.

## Gotchas
- pnpm strict hoisting can break packages relying on phantom dependencies — use shamefully-hoist=true as escape hatch
- pnpm-lock.yaml is not compatible with npm/yarn lockfiles

## Related
- nx-monorepo-setup, turborepo-setup, nvm-node-version-manager
