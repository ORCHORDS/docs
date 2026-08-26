# Android 16 Edge-to-Edge Inset Migration

**Issue:** Apps targeting newer Android releases can render beneath status, navigation, and cutout areas; screens that relied on historical system-bar padding may hide controls or produce inconsistent layouts.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Treat edge-to-edge as the layout model, not a last-minute padding patch. Keep decorative backgrounds behind system bars while applying the relevant `WindowInsetsCompat` types to interactive/content containers. Decide separately whether each view consumes system bars, display cutout, mandatory gestures, IME, and tappable-element insets.

Make inset application idempotent: derive padding/margins from captured baseline values rather than adding repeatedly on every dispatch. For scrolling containers, use clipping behavior that lets content draw behind bars while keeping first/last interactive items reachable. Update contrast and system-bar icon appearance for light/dark backgrounds.

Remove version opt-outs only after every activity, dialog, bottom sheet, web view, and Compose/View bridge is audited. Keep accessibility touch targets and gesture exclusion narrow.

## Verification

Test gesture and three-button navigation; portrait, landscape, foldables, cutouts, freeform/multi-window; IME shown/hidden; light/dark mode; font/display scaling; and Android versions before and after enforcement. Use screenshot tests plus interaction tests for top/bottom controls, scrolling endpoints, transient bars, and keyboard focus. Confirm no inset doubles after configuration changes.

## Gotchas

Applying one “system bars” padding to the root often creates excessive space and breaks immersive surfaces. Insets change over time and may be zero on some edges. Edge-to-edge correctness is a screen-by-screen responsibility, not proof that content merely avoids overlap on one emulator.

## Sources

- [Android 16 behavior changes](https://developer.android.com/about/versions/16/behavior-changes-16)
- [Android edge-to-edge guidance for Views](https://developer.android.com/develop/ui/views/layout/edge-to-edge)
- [Android WindowInsetsCompat reference](https://developer.android.com/reference/androidx/core/view/WindowInsetsCompat)
