# Android Large-Screen Orientation and Resizability Migration

**Issue:** On Android 16 large screens, orientation, aspect-ratio, and resizability restrictions can be ignored, exposing fixed-phone layouts to landscape, split-screen, foldable, and desktop-sized windows.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Treat window size—not device model or current orientation—as the layout input. Build adaptive panes and navigation around canonical window-size classes, and keep important controls reachable at every intermediate resize. Preserve UI and task state across configuration change, window resize, fold/unfold, and process recreation.

Audit manifest attributes and runtime orientation requests as compatibility hints rather than layout guarantees. Remove width assumptions, stretched single columns, fixed-position dialogs, and bitmap-only assets. Use constraint-based or Compose adaptive layouts, sensible content maximum widths, and accessible focus traversal when panes appear/disappear.

Use the Android 16 compatibility opt-out only as a short migration bridge with an owner and removal milestone; Android guidance notes later platform behavior becomes stricter. Test libraries, ad/payment SDK screens, web content, and authentication flows—not just the home activity.

## Verification

Run resizable-emulator and physical-device tests across portrait/landscape, split-screen, freeform windows, external display, fold/unfold, smallest width around 600dp, font/display scaling, keyboard/mouse, and process death. Assert state restoration, no clipped controls, readable line length, stable back behavior, correct dialogs, and no duplicate network mutation after recreation.

## Gotchas

A tablet screenshot at one size is not adaptive proof. Configuration-change suppression shifts lifecycle responsibility to the app and often hides bugs. Screen orientation can still matter for sensors/media, but must not be the sole layout branch.

## Sources

- [Android 16 large-screen behavior changes](https://developer.android.com/about/versions/16/behavior-changes-16#adaptive-layouts)
- [Android adaptive app guidance](https://developer.android.com/develop/adaptive-apps)
- [Android adaptive do's and don'ts](https://developer.android.com/develop/adaptive-apps/guides/adaptive-dos-and-donts)
