# Git worktree branch-reset safeguards

**Issue:** Using git worktree add -B can reset an existing branch to another commit and discard its previous reachability assumptions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Treat -B as a destructive branch movement, not a convenience spelling of -b. Resolve the current branch object ID, verify it is not checked out or protected, record the intended start point, and use compare-and-swap branch updates where automation permits. Prefer a new uniquely named branch when preservation matters. Keep reflog retention and remote-protection policy as recovery layers, not authorization.

## Verification

Test existing, missing, protected, checked-out, merged, and unpushed branches. Simulate a stale plan where the branch advances between preview and execution and require refusal. Verify reflog-based recovery in a disposable repository.

## Gotchas

- Pin and verify exact platform versions before rollout.
- Preserve reproducible diagnostics without secrets or personal data.
- Define rollback and stop conditions before production use.

## Official source

- [Primary documentation](https://git-scm.com/docs/git-worktree)
