# android-16-adaptive-large-screens

**Issue:** Apps targeting Android 16 can break on tablets, foldables, or desktop windows when layouts assume a fixed portrait phone shape.
**Date:** 2026-08-26
**Status:** documented
**Source:** https://developer.android.com/develop/adaptive-apps/guides/app-orientation-aspect-ratio-resizability

## Context
For apps targeting Android 16 (API 36), Android changes large-screen behavior on displays with smallest width of at least 600dp. Orientation, aspect-ratio, and resizability restrictions can be ignored so the app fills the available window.

## Pattern
- Design from the app window size, not a presumed device orientation.
- Use responsive/adaptive layouts and window size classes.
- Allow scrolling where reduced height could otherwise hide actions.
- Test portrait, landscape, split screen, fold/unfold transitions, and desktop-style resizing.
- Check camera previews and media surfaces for aspect-ratio assumptions.
- Avoid hard-coded layout widths that stretch badly on expanded displays.

## Migration checks
Review uses of:
- `screenOrientation`
- `resizeableActivity`
- `minAspectRatio`
- `maxAspectRatio`
- `setRequestedOrientation()`

For API 36 large-screen targets, relying on these to preserve a phone-only layout is not a durable strategy.

## Verification
Test representative compact, medium, and expanded windows. Verify that navigation, dialogs, forms, media, and primary actions remain reachable and visually coherent after live resize and rotation.

## Gotchas
- A layout that looks correct on a phone emulator can still fail on a 600dp+ window.
- Letterboxing assumptions are increasingly unsafe as Android moves toward universally adaptive behavior.
- Android documentation states that the opt-out capability is removed for API 37+ large-screen behavior.

## Related
- `android-16-predictive-back-migration.md`
- `android-foldables.md`
- `android-multi-window.md`
