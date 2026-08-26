# Android Live Update Notification Eligibility

**Issue:** Promoting ordinary alerts as Live Updates creates persistent notification noise, while malformed progress state can leave prominent system surfaces stale.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Use a Live Update only for a user-initiated, finite, actively trackable experience such as navigation, delivery, or a timed journey. Do not use it for recommendations, bundled unrelated activity, open-ended background work, or custom promotional visuals.

Use an eligible notification style and maintain one stable notification identity for the activity. Update concise progress and estimated completion only from authoritative state; stop promotion and post the terminal state promptly on completion, cancellation, or failure. Respect notification permission, channel controls, user demotion/dismissal, and system eligibility decisions.

Rate-limit updates and avoid wakeups for cosmetic progress. Deep links must resolve to the correct authenticated activity without trusting notification extras as authorization.

## Verification

Test qualifying/nonqualifying styles, permission denial, user demotion and dismissal, process death, reboot, offline/stale progress, completion/failure/cancel, multiple concurrent activities, lock screen privacy, accessibility, and deep-link tenant isolation. Confirm stale Live Updates are removed.

## Gotchas

The system decides promotion and users can demote it. Prominence is not guaranteed delivery. Do not expose sensitive destination, health, or payment detail on the lock screen.

## Sources

- [Android create Live Update notifications](https://developer.android.com/develop/ui/views/notifications/live-update)
- [Android Live Update design guidance](https://developer.android.com/design/ui/mobile/guides/home-screen/live-updates)
