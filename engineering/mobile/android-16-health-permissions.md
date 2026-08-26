# Android 16 health permission migration

**Date:** 2026-08-26
**Status:** documented
**Source:** https://developer.android.com/about/versions/16/behavior-changes-16

## Context

Apps targeting Android 16 (API 36) that previously used `BODY_SENSORS` or `BODY_SENSORS_BACKGROUND` need to account for Android's granular health permissions.

## Current Android 16 behavior

- APIs that previously required the broad body-sensor permissions can require corresponding permissions under `android.permissions.health`.
- A heart-rate use case can require `READ_HEART_RATE` instead of `BODY_SENSORS`.
- Background health-data access can require `READ_HEALTH_DATA_IN_BACKGROUND` instead of `BODY_SENSORS_BACKGROUND`.
- Mobile apps using these health permissions must provide the required privacy-policy/rationale surface described by Android guidance.

## Migration pattern

1. Inventory every sensor and health API used by the app.
2. Map each API to its current granular permission rather than mechanically carrying old permissions forward.
3. Test denial, revocation, while-in-use, and background-access behavior separately.
4. Keep the privacy-policy activity reachable and aligned with the actual data use.
5. Verify on API 36 before increasing `targetSdkVersion`.

## Anti-patterns

- Treating `BODY_SENSORS` as a permanent compatibility umbrella.
- Assuming foreground and background health access use the same permission.
- Requesting health permissions without an in-product rationale and privacy-policy path.

## Verification

Use an API 36 test device/emulator, revoke permissions between cases, and prove each protected path fails safely when access is denied.

## Related

- `android-permissions-best-practices.md`
- `android-health-connect.md`
