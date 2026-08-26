# Git reftable migration verification

**Issue**

Migrating the shared reference store changes the backend used by every linked worktree and can affect older tools, reflogs, recovery, and concurrent ref writers.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Inventory every Git and library client before selecting reftable.
- Quiesce writers and run `git refs migrate --dry-run` first.
- Preserve reflogs unless an approved retention decision says otherwise.
- Back up repository administrative data and define backend rollback.

## Verification

1. Run strict refs verification and fsck before and after migration.
2. Exercise branch, tag, fetch, push, worktree add/remove, and reflog recovery.
3. Open every linked worktree with the oldest supported client.
4. Interrupt only in a disposable fault-injection copy.

## Gotchas

- A dry run writes a separate candidate store but does not prove tool compatibility.
- `--no-reflog` is destructive to recovery history.
- The reference store is shared across worktrees.

## Official source

- [Official documentation](https://git-scm.com/docs/git-refs)
