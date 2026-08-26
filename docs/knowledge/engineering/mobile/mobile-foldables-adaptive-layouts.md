# mobile-foldables-adaptive-layouts

**Issue:** Foldables, tablets, and desktop-windowed environments have broken the assumption that a phone app gets one roughly phone-shaped window. An app opened on a Galaxy Fold can be compact when folded, medium when unfolded, and expanded in split-screen — sometimes within one session, mid-interaction, at the hinge. Apps built only for compact phone screens render as stretched, letterboxed, or half-empty UI on large screens, which now carry real distribution weight: Google Play ranks large-screen quality, and iPad-class devices dominate tablet markets. Engineering adaptive layouts means designing around window size classes and fold postures rather than device models.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Window size classes

1. **Classify the window, not the device.** Window size classes (Compact, Medium, Expanded for width and height) are computed from the current window's bounding box, not the physical screen. A tablet in split-screen gives your app a compact window even though the hardware is large, so branching on device model or screen diagonal is always wrong.
2. **Width is the primary axis.** The canonical breakpoints are Compact width (0-599dp), Medium (600-839dp), and Expanded (840dp+). Use width for layout decisions (single column vs list-detail) and height only for special cases like landscape phones.
3. **Recomposition, not restart.** Fold and unfold, rotation, and window resizing in multi-window deliver configuration changes. Handle size-class changes as live recomposition (or resize events) — losing scroll position and form state on fold is the most common foldable UX bug.
4. **Design for the expansion moment.** The canonical foldable journey starts folded (compact) and unfolds (medium/expanded). Persist navigation state so the detail pane of a list-detail layout shows what the user was just viewing in the single-column layout.

## Material 3 Adaptive components

1. **Use the Jetpack compose-material3-adaptive library.** Now stable, it provides canonical adaptive building blocks: NavigationSuiteScaffold (bottom nav in compact, rail in medium, sidebar in expanded), ListDetailPaneScaffold, and SupportingPaneScaffold. Building these by hand invites inconsistent breakpoints.
2. **List-detail is the workhorse pattern.** On compact show list, then detail as a separate screen; on medium/expanded show both panes with the detail embedded. ListDetailPaneScaffold handles pane expansion and back navigation (predictive back included) across the transition.
3. **Canonical extra-large layouts.** Beyond list-detail, the Material 3 guidance (supporting pane, expanded dialog, and the gallery-style feed/detail layouts) covers most content apps; mixing more than two primary zones on a tablet rarely helps.
4. **Views apps are not excluded.** WindowManager's WindowMetricsCalculator and the material3-adaptive navigation suite have View-compatible counterparts; the same breakpoints apply, so the design language stays consistent across codebases.

## Fold posture awareness

1. **Read the hinge through WindowInfoTracker.** The Jetpack WindowManager library exposes FoldingFeature (state HALF_OPENED/FULL, orientation, and bounds) via WindowInfoTrackerCallbackAdapter or flow-based APIs. On a half-opened fold, the hinge is a physical boundary users treat like a laptop seam.
2. **Tabletop and book modes.** HALF_OPENED horizontal hinge means tabletop (video content on top half, controls below); HALF_OPENED vertical hinge means book mode (content in one half). Move controls, camera preview, or forms away from the hinge line — a button under the hinge is physically untappable.
3. **Avoid putting anything critical on the crease.** Treat the hinge bounds like a display cutout: respect it via avoid-area padding for interactive elements, but let background content span it so the app does not look like two apps glued together.

## Cross-platform and testing

1. **iPadOS has the same problem.** iPad multitasking (Split View, Slide Over) resizes windows arbitrarily; size classes (UIScene sizeClass and UITraitCollection) drive the same compact/regular decisions. SwiftUI's NavigationSplitView is the direct analogue of ListDetailPaneScaffold.
2. **React Native and Flutter need resizes forwarded.** RN's useWindowDimensions updates live; Flutter exposes widget constraints — but check that the framework's responsive helpers react to mid-session window resizing, not just initial load, especially inside Capacitor/WebViews where only CSS media queries see the change.
3. **Test with resizing emulators.** Android Studio's resizable emulator profile lets you drag window sizes, simulate fold/unfold, hinge postures, and desktop windows without owning hardware; combine with real-device passes on at least one foldable before shipping large-screen claims.
4. **Audit letterboxing.** If the manifest or Play Console large-screen compatibility settings restrict resize, Android letterboxes the app — visible black bars. Remove fixed aspect ratios and orientation locks so the app participates in multi-window instead.
5. **Measure large-screen quality.** Google Play's large-screen app quality tiers (basic/advanced/optimal) checklist — plus Coreperf vitals — is the external bar; run through it before claiming foldable support in release notes.
