# git-submodules

**Issue:** Shared library code duplicated across repos or managed inconsistently
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Common utilities copied and pasted; no way to get updates without manual copying.

## Pattern / Solution
git submodule add URL path/to/sub. Clone with submodules: git clone --recurse-submodules. Update: git submodule update --remote. Pin to specific commit in parent repo. Commit .gitmodules and submodule pointer.

## Gotchas
- Submodule pointer is a specific commit, not a branch — explicit update needed to advance
- Prefer package managers over submodules for most cases; submodules are for code you modify

## Related
- pnpm-workspace-setup, nx-monorepo-setup
