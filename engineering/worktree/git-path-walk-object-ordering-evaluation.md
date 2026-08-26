# Git path-walk object-ordering evaluation

**Issue**

Path-based object traversal can change pack construction performance and layout, so adoption needs repository-specific evidence rather than a global tuning assumption.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin Git and enable path-walk only in an isolated maintenance or packing experiment.
- Keep correctness checks and a rollback to default traversal.
- Measure pack size, CPU, memory, clone, and fetch performance together.

## Verification

1. Build packs from identical refs with both traversals.
2. Run fsck and representative clones/fetches.
3. Repeat for monorepo, binary-heavy, and high-churn histories.

## Gotchas

- Smaller pack is not always faster to generate or fetch.
- Heuristics evolve by Git version.
- Do not run competing pack maintenance concurrently.

## Official source

- [Official documentation](https://git-scm.com/docs/git-pack-objects)
