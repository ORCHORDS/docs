# Git built-in fsmonitor correctness and performance

**Issue:** Scanning every path for each status-sensitive command is expensive in large worktrees, but filesystem monitoring has platform and mount limitations.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Git's built-in fsmonitor daemon watches a worktree using platform notification facilities and lets commands such as `git status` query recent changes instead of rescanning every path. With `core.fsmonitor=true`, supported commands can start and use the daemon automatically.

Validate filesystem support before rollout. Git refuses remote-mounted repositories by default; overriding that behavior is experimental. Linux deployments must also account for per-user inotify watch limits.

## Operational controls

- Pin a supported Git version and test every runner filesystem type.
- Monitor daemon status and fall back safely to full scanning on failure.
- Do not raise inotify limits blindly; measure directory counts and host-wide consumers.
- Check linked worktrees and submodules for performance and lifecycle behavior.
- Stop orphaned daemons when ephemeral worktrees are removed.
- Keep authoritative clean-tree checks capable of running with fsmonitor disabled.

## Verification

1. Compare `status` latency and output with fsmonitor enabled and disabled.
2. Modify, rename, and delete files rapidly and confirm every change appears.
3. Test daemon restart and event overflow behavior.
4. Exercise submodules and linked worktrees used by the project.
5. Validate teardown leaves no unwanted long-running process.

## Sources

- [Git: git-fsmonitor--daemon](https://git-scm.com/docs/git-fsmonitor--daemon)
- [Git: update-index filesystem monitor](https://git-scm.com/docs/git-update-index)
