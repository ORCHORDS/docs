# Git reference-database verification gate

**Issue**

Corrupt, malformed, or backend-inconsistent refs can make parallel worktrees resolve branches differently or fail during checkout, fetch, and cleanup.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Run `git refs verify --strict` as a maintenance gate on a pinned Git version before high-concurrency automation.
- Quiesce ref-writing jobs or take a consistent repository snapshot before interpreting verification results.
- Pair reference verification with `git fsck` because ref existence and object reachability are different properties.
- Capture backend format, common Git directory, failing ref, and exit status without dumping sensitive ref namespaces.
- Repair through supported ref transactions or restore procedures; never edit packed refs or reftable files ad hoc.

## Verification

1. Seed malformed and dangling refs in disposable repositories and distinguish verification from object-integrity failures.
2. Test files and reftable backends where supported.
3. Run from the main and linked worktrees and confirm they inspect the shared reference database.
4. After repair, rerun strict verification, fsck, and representative checkout/fetch operations.

## Gotchas

- `git refs exists` does not prove the ref resolves to an object.
- Strict verification can promote warnings to errors after a Git upgrade.
- Concurrent ref mutation can make an uncoordinated check misleading.
- Low-level repair can destroy reflog or atomicity guarantees.

## Official source

- [Official documentation](https://git-scm.com/docs/git-refs)
