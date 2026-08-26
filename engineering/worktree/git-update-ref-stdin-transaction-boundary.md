# Git update-ref stdin transaction boundary

**Issue:** Automation that moves several branches or symbolic refs one command at a time can leave a partially published namespace when an expected old object ID changes or a later lock fails.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `git update-ref --stdin` with explicit `start`, queued update/create/delete/verify operations, `prepare`, and `commit` when the writer requires all selected refs to pass validation together.
- Supply every expected old object ID as a compare-and-swap guard. Use a zero old ID when creation must prove absence.
- Include symbolic refs with the `symref-*` commands when they belong to the same transaction, and use `no-deref` only when changing the symbolic ref itself is intended.
- Abort on any preparation error and treat an ended stdin session without commit as failed. Record approved before/after IDs and a bounded reflog reason.
- Serialize higher-level publishers even though ref locking is transactional.

## Verification

Test successful mixed direct/symbolic updates, stale old IDs, duplicate refs, a lock held by another process, absent-create verification, delete verification, abort after prepare, process death, and retry. Assert all refs retain their old IDs on transaction failure.

## Gotchas

- Each ref update is atomic, but a concurrent reader may still observe only a subset of a committed multi-ref transaction.
- Object existence and ref authorization must be checked separately.
- A ref transaction does not update any linked working tree or index.

## Official source

- [Git update-ref --stdin transactions](https://git-scm.com/docs/git-update-ref)
