# android-edge-to-edge-enforcement

**Issue:** Starting with Android 15 (API 35), any app that targets SDK 35 or higher is forced into edge-to-edge drawing: content renders behind the status bar, navigation bar, and display cutouts, and the old opt-out flags are ignored. Apps that hard-coded status bar heights, relied on the system window fitting content, or drew opaque system bar backgrounds suddenly ship with text under the clock, buttons under the gesture bar, and inputs hidden behind the keyboard. Every Android app updating its target SDK (which Google Play requires annually) must now do explicit WindowInsets handling on every screen, in Views, Compose, and cross-platform shells alike.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What changed in Android 15

1. **Enforced, not opt-in.** With targetSdk 35 on an Android 15+ device, the system no longer fits content inside the system bars. windowOptOutEdgeToEdgeEnforcement exists only as a temporary opt-out on some device types (notably not on large screens >= 600dp) and disappears in later releases — treat migration as mandatory.
2. **Old status bar tricks are dead.** Setting statusBarColor and navigationBarColor to opaque colors is deprecated and ignored on Android 15+; scrim colors no longer create the black bar apps used to rely on. The replacement is drawing your own background behind the bars and applying insets as padding.
3. **Apps targeting older SDKs still break.** On Android 15 devices, even apps targeting API 34 get edge-to-edge behavior when they had previously opted in via WindowCompat.setDecorFitsSystemWindows(window, false) — and users on 15-inch tablets and foldables see enforcement earliest, so the blast radius is larger than the targetSdk bump alone suggests.

## Insets handling strategy

1. **Always go through WindowInsetsCompat.** Consume safeDrawingInsets (or the typed systemBars(), displayCutout(), ime() insets) inside a ViewCompat.setOnApplyWindowInsetsListener instead of reading static sizes. Cutout positions, gesture vs 3-button nav, and keyboard presence all change insets at runtime.
2. **Apply insets as padding, not margins.** Padding keeps the container background (and your brand color or map) drawing under the transparent system bars, while margins would leave an unsightly band. Use ViewCompat.setOnApplyWindowInsetsListener to set paddingTop on the root or per-toolbar padding as needed.
3. **Use max insets when layering.** When both a top bar and a cutout overlap, take the max of systemBars and displayCutout values per edge rather than adding them, or content gets pushed twice as far as it should.
4. **In Compose, compose with insets modifiers.** Modifier.windowInsetsPadding(WindowInsets.safeDrawing) on the scaffold content, or Scaffold(contentWindowInsets = WindowInsets.safeDrawing) keeps everything aligned while letting scrollable content draw edge-to-edge behind bars for the desired visual effect.
5. **Handle the IME explicitly.** With edge-to-edge, adjustResize alone no longer guarantees the keyboard pushes content up. Merge WindowInsets.ime with systemBars insets (ime insets already include nav bar height) and animate padding with the keyboard for chat and form screens.

## Navigation bar and gesture specifics

1. **Three nav modes have different heights.** Gesture navigation, 2-button, and 3-button back/home/recents produce different bottom insets; never assume 48dp. Read the insets on every screen entry because users switch modes in system settings at runtime.
2. **Contrast is the developer's job.** The transparent nav area now shows your content. For light screens with gesture nav, set isAppearanceLightNavigationBars = true so the system draws dark icons; for 3-button mode on light backgrounds, add a translucent scrim gradient yourself since button glyphs are light by default.
3. **Tappable targets need inset-aware bottom padding.** Bottom navigation, FABs, and banners must respect bottom insets or they sit under the gesture pill; a Modifier.navigationBarsPadding() (Compose) or insets listener padding (Views) is the minimum fix.

## Common bugs and testing

1. **The classic symptom is text under the clock.** If a toolbar overlaps the status bar after the targetSdk 35 bump, the screen is missing top inset padding — fix with safeDrawing top padding on the toolbar container, not by guessing dp values.
2. **Cross-platform shells need the upgrade too.** React Native (edge-to-edge enabled by default on new architecture for targetSdk 35), Flutter (SafeArea + enableEdgeToEdge), and Capacitor WebViews all need native insets forwarded to the web layer as CSS safe-area-inset variables, or the WebView content hides behind bars.
3. **Test the matrix.** Verify each screen with gesture nav, 3-button nav, a display cutout (corner punch-hole), keyboard open/close, landscape, and split-screen/multi-window, where insets differ again. Use Android 15+ emulators or Developer Options "Display cutout" simulations.
4. **Screenshot-test insets.** Because inset math is pixel-layout logic, add screenshot tests (Paparazzi/Roborazzi) for key screens with mocked inset values to catch regressions before device testing.
