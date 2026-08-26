# Git commit-graph Bloom filters for path history

**Issue:** Path-limited history queries can traverse large commit histories even when few commits touch the requested path.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Git commit-graphs can store changed-path Bloom filters that accelerate compatible path-history queries by quickly rejecting commits unlikely to touch a path. They are probabilistic filters: false positives cost work, but false negatives must not change results.

## Controls and verification

- Pin a supported Git version across writers/readers.
- Generate and maintain commit-graphs through reviewed maintenance.
- Measure write cost, disk usage, and query benefit.
- Verify split commit-graph lifecycle in frequently fetched repositories.
- Keep a safe path to delete and regenerate graph files.
- Compare query results with commit-graph use disabled.

## Sources

- [Git: commit-graph format](https://git-scm.com/docs/commit-graph)
- [Git: git-commit-graph](https://git-scm.com/docs/git-commit-graph)
