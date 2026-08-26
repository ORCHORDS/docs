# gitflow-vs-trunk

**Issue:** Team unclear on branching strategy — gitflow vs trunk-based development
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Long-lived feature branches cause merge conflicts; or trunk has no structure.

## Pattern / Solution
Trunk-based: short-lived feature branches under 2 days, feature flags for incomplete work, main always deployable. Gitflow: develop, release, hotfix branches — suitable for scheduled releases.

## Gotchas
- Gitflow merge conflicts compound over time; avoid for continuous deployment
- Trunk-based requires strong CI/CD and feature flag infrastructure

## Related
- git-worktree-patterns, git-interactive-rebase, conventional-commits
