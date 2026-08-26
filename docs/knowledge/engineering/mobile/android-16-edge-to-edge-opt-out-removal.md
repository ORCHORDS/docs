# Android 16 edge-to-edge opt-out removal

**Date:** 2026-08-26
**Status:** documented
**Source:** https://developer.android.com/about/versions/16/behavior-changes-16

## Context

Apps targeting Android 16 (API level 36) can no longer rely on the Android 15 edge-to-edge opt-out when running on Android 16.

## Current platform behavior

Android 16 disables `R.attr.windowOptOutEdgeToEdgeEnforcement` for apps targeting API level 36 on Android 16 devices. The attribute is deprecated for this target level.

An app targeting API level 36 can still see the old opt-out work when that app runs on Android 15, which makes mixed-device testing important.

## Migration pattern

- Remove assumptions that the app can opt out of edge-to-edge on Android 16.
- Handle system-bar insets explicitly in layouts that would otherwise be obscured.
- Test navigation, bottom bars, dialogs, forms, keyboards, and full-screen content with gesture and three-button navigation.
- Test API-36-targeted builds on both Android 15 and Android 16 because opt-out behavior differs by runtime OS.
- Treat edge-to-edge readiness as a target-SDK migration requirement rather than a cosmetic enhancement.

## Verification

For an API level 36 target on Android 16:

1. Confirm content is not unintentionally hidden behind status or navigation bars.
2. Confirm tappable controls remain reachable near system-bar areas.
3. Confirm keyboard/inset handling remains correct after rotation and window resizing.
4. Remove reliance on `windowOptOutEdgeToEdgeEnforcement` as a production fix.

## Gotchas

- A build that looks correct on Android 15 can still fail after moving to Android 16 because the opt-out is disabled there.
- Edge-to-edge defects often show up as clipped controls or incorrect padding rather than crashes.

## Related

- `android-16-adaptive-large-screens.md`
- `android-16-predictive-back-migration.md`
