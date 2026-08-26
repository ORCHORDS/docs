# Git background maintenance for large worktrees

**Issue:** Large, long-lived repositories and worktrees accumulate object and metadata costs that slow fetch, status, and history operations when maintenance is only reactive.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Use `git maintenance start` or an explicitly managed `git maintenance run --scheduled` policy to move safe repository optimization away from foreground developer and runner commands. Git's incremental maintenance strategy schedules commit-graph and prefetch work more frequently and loose-object and incremental-repack work less frequently.

A linked-worktree setup shares the repository object database, so coordinate maintenance at repository scope. Do not launch independent aggressive garbage collection from every worktree or concurrent CI job.

## Operational controls

- Check the installed Git version and scheduler support before enabling maintenance fleet-wide.
- Decide whether Git's scheduler or existing host automation owns the schedule; avoid duplicate schedulers.
- Run maintenance under the account that owns the repository and its Git configuration.
- Bound CPU and I/O impact on shared self-hosted runners and avoid peak build windows.
- Monitor disk usage and command latency before and after rollout.
- Use `git maintenance stop` for the scheduler and `unregister` when removing a repository from managed maintenance.

## Verification

1. Record baseline timings for representative `fetch`, `status`, and history queries.
2. Register a test repository and inspect the resulting maintenance configuration and scheduler entry.
3. Run scheduled maintenance and verify foreground worktrees remain usable.
4. Confirm concurrent work does not produce lock failures or repository corruption.
5. Test stop and unregister behavior as part of runner decommissioning.

## Sources

- [Git: git-maintenance](https://git-scm.com/docs/git-maintenance)
- [Git: git-worktree](https://git-scm.com/docs/git-worktree)
