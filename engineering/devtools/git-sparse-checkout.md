# git-sparse-checkout

**Issue:** Monorepo checkout is slow and huge; developers only need part of it
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
50GB monorepo takes 20 minutes to clone and uses excessive disk on developer machines.

## Pattern / Solution
git clone --filter=blob:none --sparse URL. git sparse-checkout set apps/web packages/ui. Only listed paths are checked out; others are absent locally. Works with cone mode for directory-based selection.

## Gotchas
- Some tools may break when expected files are absent
- --filter=blob:none (blobless) vs --filter=tree:0 (treeless) — different tradeoffs

## Related
- git-worktree-patterns, nx-monorepo-setup, turborepo-setup
