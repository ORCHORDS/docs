# Android user-initiated data transfer jobs

**Issue:** A large upload or download started by a person is forced into ordinary background work or a manual wake lock. It is then delayed, killed without a resumable checkpoint, or kept alive with the wrong user visibility and battery semantics.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published; API-level gate required

## Controls and implementation

Use a User-Initiated Data Transfer (UIDT) job only for a transfer directly started by the person that should begin immediately and remain visibly tracked. Declare the documented job service and `RUN_USER_INITIATED_JOBS` permission, mark the JobInfo user-initiated, and call `setNotification` promptly with localized progress and a graceful cancel action.

Persist an operation ID, byte/range checkpoint, validators, destination, and integrity state before scheduling. Make chunks resumable and completion idempotent. Use WorkManager for deferrable or background-initiated transfers and a documented compatibility path on unsupported OS versions.

## Verification

Test scheduling while visible and from disallowed background states, user cancellation, system stop, process death, reboot, low memory, thermal pressure, metered/unmetered changes, expired upload sessions, range mismatch, duplicate scheduling, and unsupported versions. Verify restart resumes from durable state rather than duplicating bytes or finalization.

## Gotchas

Stopping from Android's Task Manager can terminate the process without calling `onStopJob()`; checkpoints cannot live only in memory. UIDT jobs are for data transfer, not arbitrary long computation, and user visibility does not guarantee uninterrupted execution.

## Sources

- Android Developers, [User-initiated data transfer](https://developer.android.com/develop/background-work/background-tasks/uidt)
- Android Developers, [Data transfer background task options](https://developer.android.com/develop/background-work/background-tasks/data-transfer-options)
