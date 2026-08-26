# android-16-predictive-back-migration

**Issue:** Back navigation code that relies on legacy `onBackPressed()` or raw `KEYCODE_BACK` handling can stop behaving as expected when an app targets Android 16 (API level 36).
**Date:** 2026-08-26
**Status:** documented
**Primary sources:** Android Developers

## Current platform behavior

For apps targeting Android 16 (API level 36) or higher and running on Android 16 or higher, Android enables predictive-back system animations by default. Android's current behavior-change documentation states that legacy `onBackPressed` is not called and `KeyEvent.KEYCODE_BACK` is not dispatched in this configuration.

Android recommends migrating back handling to supported APIs. A temporary opt-out is available through `android:enableOnBackInvokedCallback="false"`, but that is a migration aid rather than a durable design target.

## Migration pattern

Prefer AndroidX back handling where possible so navigation behavior remains compatible across platform releases.

For activity or fragment code, use `OnBackPressedDispatcher` / `OnBackPressedCallback` rather than overriding legacy back events.

For Jetpack Compose, use the current Navigation Compose and predictive-back APIs instead of intercepting raw back key events.

When custom transitions are used, verify that the user can preview the destination and cancel the gesture without leaving navigation state partially mutated.

## Test matrix

At minimum, exercise:

- back-to-home from the root activity;
- cross-activity navigation;
- cross-task navigation where the app uses multiple tasks;
- nested navigation stacks;
- modal, drawer, sheet, and search surfaces that intercept back;
- gesture cancellation partway through the predictive-back animation;
- state restoration after process recreation;
- Android 15 and Android 16 devices or emulators;
- the app both before and after raising `targetSdkVersion` to API 36.

Android's compatibility framework can be used to force-enable or disable supported behavior changes during testing without immediately changing the app target SDK, which is useful for isolating migration failures.

## Edge-to-edge interaction

Android's predictive-back design guidance also calls out system gesture insets. Do not place custom drag targets or critical touch controls entirely inside system gesture regions. Android 16 also removes the edge-to-edge opt-out for apps targeting API 36 when they run on Android 16, so predictive-back and window-inset testing should be performed together.

## Gotchas

- Do not assume a working hardware-back-key test proves gesture navigation is correct.
- Do not mutate irreversible navigation state at gesture start; the user can cancel a predictive-back gesture.
- Avoid root-activity interception that prevents the system back-to-home animation unless there is a documented product requirement and supported implementation.
- Treat `android:enableOnBackInvokedCallback="false"` as temporary compatibility debt and track its removal.
- Re-test custom navigation libraries when changing target SDK because platform dispatch behavior changes at API 36.

## Sources

- Android Developers — Behavior changes: Apps targeting Android 16 or higher: https://developer.android.com/about/versions/16/behavior-changes-16
- Android Developers — Add support for the predictive back gesture: https://developer.android.com/guide/navigation/custom-back/predictive-back-gesture
- Android Developers — Predictive back design: https://developer.android.com/design/ui/mobile/guides/patterns/predictive-back
- Android Developers — Compatibility framework changes (Android 16): https://developer.android.com/about/versions/16/reference/compat-framework-changes

## Related

- Review existing Android navigation, edge-to-edge, gesture-inset, and target-SDK migration articles before adding overlapping guidance.
