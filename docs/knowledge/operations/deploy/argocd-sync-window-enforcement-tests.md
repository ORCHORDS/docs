# Argo CD sync-window enforcement tests

**Issue**

Sync windows can block or allow automated deployment by schedule, application, namespace, or cluster, but overlapping windows and manual-sync settings can yield a different effective policy than a reviewer expects.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Define deny windows for freeze periods and narrowly scoped allow windows for approved automation.
- Specify timezone assumptions in operational policy and review daylight-saving transitions.
- Treat `manualSync` overrides as privileged change paths with audit and approval.
- Test selectors against real application destinations and names; avoid broad wildcard changes without impact output.
- Keep emergency procedures separate from deleting or weakening the window resource.

## Verification

1. Use Argo CD's effective-window inspection for representative applications before merge.
2. Test immediately before, during, and after every boundary, including overlapping allow and deny windows.
3. Attempt automated and manual syncs and assert the intended distinction.
4. Exercise controller restart and clock-skew monitoring during an active freeze.

## Gotchas

- A window controls sync permission, not health assessment or already-running hooks.
- Overlapping active windows must be evaluated together.
- Cron schedules and durations can create unintended gaps or continuous coverage.
- Repository changes may continue accumulating while sync is denied.

## Official source

- [Official documentation](https://argo-cd.readthedocs.io/en/stable/user-guide/sync_windows/)
