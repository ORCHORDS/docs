# Git multi-pack-index verification and compaction

**Issue:** Repositories with many packfiles spend extra time searching pack indexes and accumulate inefficient object storage.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

A Git multi-pack-index indexes objects across multiple packfiles. Use supported write, verify, repack, and expire steps through a version-aware maintenance policy. Some modes and formats have version compatibility constraints.

## Controls and verification

- Pin the minimum Git version for every reader.
- Run `git multi-pack-index verify` before and after maintenance.
- Keep concurrent object writers in the safety model.
- Measure fetch and object lookup latency and disk use.
- Do not mix incompatible incremental and expire/repack modes.
- Back up or retain the ability to regenerate derived index files.

## Sources

- [Git: git-multi-pack-index](https://git-scm.com/docs/git-multi-pack-index)
- [Git: Multi-pack-index design](https://git-scm.com/docs/multi-pack-index)
