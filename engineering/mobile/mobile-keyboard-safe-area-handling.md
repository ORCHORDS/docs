# mobile-keyboard-safe-area-handling

**Issue:** Chat inputs, forms, and bottom sheets that look perfect on a modern bezel-less phone suddenly break in production: content hides behind the status bar or gesture nav, the keyboard covers the input the user is typing into, or the screen jumps when the keyboard animates. The 2025 inflection point is that apps targeting Android 15 (API 35) are forced into edge-to-edge — the old `fitsSystemWindows` and theme-flag escape hatches no longer work — so inset and keyboard handling that was "wrong but invisible" for years is now visibly wrong. This article covers safe-area/inset handling on both platforms, keyboard (IME) avoidance done correctly, the Android 15 enforcement, and how WebView shells (React Native, Capacitor) surface or hide these values.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Safe areas and insets: the platform primitives

1. **iOS gives you one safe area; treat it as a floor, not a ceiling.** `UIView.safeAreaInsets` / SwiftUI's `.safeAreaInset` already account for the notch/Dynamic Island, home indicator, and (in UIKit) the keyboard when using `UIScrollView` keyboard avoidance. Content backgrounds should extend beyond the safe area (full-bleed); only interactive elements and text must be inside it.
2. **Android has no single "safe area" — it has typed insets.** `WindowInsetsCompat.Type.systemBars()`, `displayCutout()`, `tappableElement()`, and `ime()` are separate types that must be combined deliberately. In Compose, `WindowInsets.safeDrawing` is the closest equivalent to iOS's safe area (system bars + cutout + IME). Assuming any one type covers all cases is the root of most "button under the camera cutout in landscape" bugs.
3. **Landscape cutouts differ per OEM.** Display cutout policies (`shortEdges` vs `never` vs default) vary across Samsung/Xiaomi/Pixel, and some devices cut in both corners. Never hardcode pixel padding for "the notch" — always read `displayCutout()` insets at runtime and test in landscape, not just portrait.
4. **Apply insets as padding, not margins or translation.** Padding keeps the background drawable full-bleed behind system bars (the intended edge-to-edge look) while moving content in. Margins/translations shrink the background too, producing the ugly "letterboxed app" band that looks broken next to native apps.

## The Android 15 edge-to-edge enforcement (targetSdk 35+)

1. **Enforcement is unconditional for apps targeting API 35.** On Android 15+ devices, your app draws behind status and navigation bars regardless of theme attributes; `fitsSystemWindows="true"` and `window statusBarColor` strategies are ignored or deprecated. The migration is not optional — plan it the moment you raise `targetSdkVersion` (Play requires recent targets annually).
2. **Audit every screen for three failure classes.** (a) Interactive elements under the gesture bar or behind the back-gesture exclusion zone, (b) text under the status bar, (c) bottom-anchored elements (FAB, snackbars, bottom nav) overlapped by the nav bar. The Android Developers "Insets handling tips for Android 15's edge-to-edge enforcement" post covers the canonical fixes.
3. **Use the Compose modifiers instead of manual inset math.** `Modifier.statusBarsPadding()`, `.navigationBarsPadding()`, `.imePadding()`, and `.safeDrawingPadding()` compose correctly with `Scaffold` (which already applies insets to its slots). Manually reading `WindowInsets` values and adding pixel offsets leads to double-padding when a parent already consumed the insets.
4. **Watch for inset consumption bugs.** In View land, an inset listener that returns `CONSUMED` stops propagation to children — a `BottomSheet` or toolbar consuming system bar insets will starve the fragments below it of insets. This is the most common regression after enabling edge-to-edge on multi-fragment apps.

## Keyboard (IME) avoidance without jank

1. **Never use `android:windowSoftInputMode="adjustResize"` blindly on API 30+.** With edge-to-edge, the window no longer resizes for the keyboard; you must apply `ime()` insets yourself (`imePadding()` in Compose, `ViewCompat.setOnApplyWindowInsetsListener` in Views) or use `WindowInsetsAnimationCompat` to sync scrolling with the keyboard's ~300ms animation. Jumping content at the end of the animation looks broken; `imePadding()` animates with the IME.
2. **The IME inset already includes the nav bar overlap.** On gesture-nav devices, `ime()` height = keyboard height, and the keyboard covers the nav bar — so applying both `navigationBarsPadding()` and `imePadding()` sequentially (Compose: `Modifier.navigationBarsPadding().imePadding()`) is the correct pattern; `imePadding()` alone wins when the keyboard is open because of how the modifiers chain.
3. **On iOS, prefer `UIScrollView` keyboard dismissal over global frames.** UIKit scrolls the focused field into view automatically if the field is inside a scroll view and keyboard insets are set (`contentInset.bottom = keyboardFrame.height`). SwiftUI's default behavior moves the whole view; for chat-style UIs, pin the input bar with `.safeAreaInset(edge: .bottom)` inside a `ScrollView` rather than observing `NotificationCenter` keyboard frames yourself.
4. **Handle hardware and floating keyboards.** iPad floating keyboards and Android external keyboards produce zero IME inset; layouts that assume "keyboard open = push content up" will leave phantom padding if you key off keyboard visibility booleans instead of actual inset values. Always drive layout from the inset value, not from a visibility flag.
5. **Test with "show button to tap outside keyboard" and one-handed reach.** The IME inset includes accessory strips (autofill toolbar, emoji row, Samsung's extra row) that are taller than `getStatusBarHeight`-style guesses — screenshots at every keyboard state per the example project test protocol catch these.

## Cross-platform and WebView shells

1. **React Native exposes insets via `react-native-safe-area-context`.** Wrap the app in `SafeAreaProvider` and consume `useSafeAreaInsets()`; with `targetSdk 35`, RN's old `windowSoftInputMode` resize behavior changed and `android:windowSoftInputMode="adjustResize"` plus `KeyboardAvoidingView` needed re-validation. The RN community discussion #827 ("Handling Android 15 edge-to-edge on React Native") documents the flag (`WindowCompat.setDecorFitsSystemWindows(window, false)`) and edge-to-edge opt-in/edge cases.
2. **Capacitor apps must bridge insets into CSS.** Use the `@capacitor/status-bar` and safe-area plugins (or `viewport-fit=cover` + `env(safe-area-inset-*)` CSS) — the WebView does not receive native insets unless the meta viewport opts into the display cutout. On Android with edge-to-edge enforced, the WebView needs the `setDecorFitsSystemWindows(false)` path plus CSS padding, or content lands under system bars.
3. **Keyboard in WebViews: `VisualViewport` is the only reliable signal.** `window.visualViewport.resize` events fire as the keyboard opens on both platforms; the old `resize` event on `window` does not on iOS. Every in-WebView chat input should be positioned from `visualViewport.height + offsetTop`, not from legacy keyboard estimates.
4. **Screenshot both platforms with the keyboard open at every input screen.** The example project `test_step` flow (screenshot after each interaction) exists precisely because keyboard behavior differs between the S22 test device, budget devices with taller IMEs, and iOS. "Works on the emulator in portrait" is not evidence.

## Related

- `mobile-e2e-testing.md`
- `react-native-bottom-sheet.md`
- `capacitor-webview-to-native-migration.md`
- `mobile-accessibility-a11y.md`
