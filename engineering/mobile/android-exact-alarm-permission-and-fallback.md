# Android exact-alarm permission and fallback

**Issue:** Exact alarms consume significant device resources and require special permission on modern Android versions. Assuming permission persists can crash scheduling, while using exact delivery for ordinary sync wastes battery.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Use an exact alarm only when a user-facing core feature genuinely requires precise timing. Prefer WorkManager or inexact alarms for synchronization and flexible reminders, and design a visible fallback for denied or revoked exact-alarm access.

## Controls

- Document why precision is necessary and review the applicable Google Play policy.
- Choose `SCHEDULE_EXACT_ALARM` or `USE_EXACT_ALARM` only for its documented use case.
- Check `canScheduleExactAlarms()` immediately before scheduling where required.
- Explain the benefit before sending a person to special-app-access settings.
- Reschedule from durable source state after permission grant and boot; do not trust an in-memory timer list.
- Handle revocation and `SecurityException` without losing user data.
- Use immutable or appropriately scoped PendingIntents.
- Keep receiver work short and hand longer work to WorkManager or JobScheduler.
- Add jitter to network activity triggered after alarms.

## Verification

Test fresh install, upgrade, backup restore, grant, denial, revocation, reboot, Doze, battery saver, clock/time-zone changes, duplicate scheduling, and cancellation across supported API levels. Verify the fallback communicates reduced precision and that revocation cannot crash the app.

## Gotchas

Fresh installs targeting modern Android may not receive `SCHEDULE_EXACT_ALARM` by default. Exact alarms are canceled when relevant access is revoked and alarms are cleared at shutdown. Precision does not guarantee unlimited background execution.

## Sources

- [Android Developers: Schedule alarms](https://developer.android.com/develop/background-work/services/alarms)
- [Android 14 exact-alarm behavior change](https://developer.android.com/about/versions/14/behavior-changes-all#exact-alarms)
- [Android Manifest permission reference](https://developer.android.com/reference/android/Manifest.permission)
