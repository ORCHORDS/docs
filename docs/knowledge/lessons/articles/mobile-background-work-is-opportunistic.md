# Mobile background work is opportunistic, not a timer contract

**Issue:** A mobile feature promises that work will run at an exact interval even though Android and iOS schedule background execution according to system policy.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Lesson

Design background execution as an opportunity to advance durable work, not as the sole clock for a product guarantee. Persist the work intent before scheduling, make each run idempotent and resumable, and reconcile again when the app returns to the foreground.

**Sources:** [Android background tasks overview](https://developer.android.com/develop/background-work/background-tasks) · [Apple BackgroundTasks](https://developer.apple.com/documentation/backgroundtasks)

## Apply

- choose the platform API by work type instead of keeping a process alive;
- record an operation ID, prerequisites, retry state, and server checkpoint durably;
- keep handlers bounded and honor cancellation/expiration immediately;
- move deadline-critical server actions to trusted server scheduling;
- expose honest UI when refresh is pending or stale;
- resubmit only from source-of-truth state, not a chain of in-memory timers.

## Verify

Test process death before/during/after work, reboot, battery saver, denied background refresh, no network, duplicate launch, expiration, and foreground reconciliation. A repeated handler must not duplicate messages, charges, uploads, or mutations.

## Gotchas

“Earliest” execution is not “at” execution. Push notifications are hints, not guaranteed jobs. A successful scheduler submission does not mean the task ran or completed.
