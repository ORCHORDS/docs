# Android notification update coalescing and rate limits

**Issue:** Reposting rapidly changing progress or message state can repeatedly interrupt users and exceed Android’s notification update rate, causing intermediate updates to be dropped.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Coalesce state into one durable notification model, update with the same notification ID at a bounded cadence, and use `setOnlyAlertOnce(true)` when subsequent updates should not sound or vibrate again.

## Controls

- Allocate stable IDs by logical notification, not update attempt.
- Debounce or sample high-frequency progress.
- Build every update from authoritative latest state so dropped intermediates are harmless.
- Use notification groups or MessagingStyle for genuinely distinct messages.
- Keep channel importance under user control.
- Check notification permission and channel availability before posting.
- Make PendingIntents immutable unless mutation is explicitly required.
- Cancel completed or obsolete notifications deterministically.
- Do not use notification delivery as the sole record of a critical event.

## Verification

Test bursts faster than one second, out-of-order producers, app restart, process death, permission denial, channel disabled, device lock, grouping, completion, and cancellation. Confirm only the first update alerts when intended and the final visible state converges correctly even when intermediates drop.

## Gotchas

Android documents a rate limit for frequent updates but applications should not depend on a precise undocumented threshold. Reusing an ID replaces state; using new IDs creates noise. Foreground-service notification requirements still apply.

## Sources

- [Android Developers: Create and update a notification](https://developer.android.com/develop/ui/views/notifications/build-notification#Updating)
- [Android Notification FLAG_ONLY_ALERT_ONCE](https://developer.android.com/reference/android/app/Notification#FLAG_ONLY_ALERT_ONCE)
- [Android notification runtime permission](https://developer.android.com/develop/ui/views/notifications/notification-permission)
