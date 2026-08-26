# Android 16 notification auto-grouping

**Issue:** Apps targeting modern Android versions can have notifications grouped by the system even when the app does not provide its own summary.
**Date:** 2026-08-26
**Status:** documented

## Source

- Android Developers — About notifications: https://developer.android.com/develop/ui/compose/notifications

## Current behavior

Android 16 (API level 36) can automatically group notifications on an app's behalf. The Android documentation specifically notes auto-grouping for notifications without a summary, notifications without child notifications, and groups with only a small number of child notifications.

## Engineering implications

- Do not assume the visual grouping shown to users exactly matches only the grouping metadata your app explicitly created.
- Test notification-heavy flows on Android 16 devices or emulators, including apps that previously relied on many independent notifications.
- If notification ordering or grouping is business-critical, define explicit notification channels, grouping keys, summaries, and stable identifiers rather than depending on presentation side effects.
- Treat notification rendering as system-controlled UI: verify behavior instead of asserting pixel-level layouts.

## Verification checklist

- Test multiple simultaneous notifications on API 36.
- Check behavior with and without explicit group summaries.
- Confirm tapping, dismissing, and clearing grouped notifications still maps to the intended application state.
- Confirm notification analytics do not infer grouping solely from app-generated group metadata.

## Related

- `android-16-edge-to-edge-opt-out-removal.md`
- `android-16-adaptive-large-screens.md`
- `android-16-predictive-back-migration.md`
