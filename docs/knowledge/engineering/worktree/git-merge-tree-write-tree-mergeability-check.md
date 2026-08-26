# Git merge-tree write-tree mergeability check

**Issue:** A mergeability gate that performs a real checkout mutates an agent worktree, while a naive `merge-tree` wrapper can mistake conflict output for a tree ID or mishandle batch exit status.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `git merge-tree --write-tree <branch1> <branch2>` to compute the merge without changing the working tree or index. Pin the exact commits and intended merge-base policy.
- For one merge, interpret exit `0` as clean, `1` as conflicts, and any other value as an operational error. Do not collapse all nonzero statuses into ordinary conflicts.
- Parse the documented conflicted-file section, preferably with `-z`; do not scan the resulting tree for conflict markers or parse free-form informational messages as a stable API.
- With `--stdin`, parse each result because the process exit status is zero for both clean and conflicted merges when all requests were processed.
- Keep the object database disposable or subject to normal maintenance because the computation writes tree objects even though it leaves the worktree alone.

## Verification

Test a clean merge, textual and binary conflicts, rename/delete and file/directory conflicts, unrelated histories, criss-cross bases, malformed input, missing objects, and multiple stdin requests. Assert the gate reports conflict, error, and clean outcomes distinctly.

## Gotchas

- Conflict stdout contains more than a top-level tree ID.
- A clean synthetic merge does not run hooks, build, test, or validate branch protection.
- Mergeability can change when either input ref moves; report immutable object IDs.

## Official source

- [Git merge-tree](https://git-scm.com/docs/git-merge-tree)
