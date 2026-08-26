# Window Controls Overlay for desktop PWA with safe fallback

**Issue:** A desktop installed web app places content in the title-bar area without reserving operating-system window controls. Buttons become unreachable, drag regions cover interactive UI, or the layout breaks in an ordinary browser tab and on unsupported platforms.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Problem and applicability

Window Controls Overlay is an optional desktop installed-PWA display mode. It can let web content use title-bar space while the user agent retains native close, minimize, maximize, and related controls.

Use it as progressive enhancement for a desktop window shell. It does not standardize mobile chrome, make a normal browser tab frameless, or grant control over operating-system buttons.

## Controls and implementation

1. Keep a fully usable manifest display mode such as standalone, then list window-controls-overlay in display_override so unsupported agents can choose a fallback.
2. Feature-detect navigator.windowControlsOverlay before reading visibility or subscribing to geometrychange. Manifest acceptance alone does not prove the current window is using the overlay.
3. Build the default layout outside the title-bar area. Enable the compact overlay layout only when the API reports visible.
4. Use the titlebar-area CSS environment variables for geometry rather than hard-coded pixel offsets or assumptions about which side holds controls. Supply ordinary fallback values in every env expression.
5. On geometrychange, re-evaluate current visibility and bounding geometry. Coalesce layout work and remove listeners when the owning view is disposed.
6. Mark only noninteractive background regions as draggable using the supported app-region CSS mechanism. Explicitly exclude buttons, links, menus, text fields, selection areas, and resize affordances.
7. Preserve accessible names, focus order, target size, keyboard access, and a visible application title. Do not mimic or replace native close controls.
8. Treat overlay preference as window state, not user entitlement. A user or platform can disable it, and different app windows can expose different geometry.

## Verification

Test installed and browser-tab launches, overlay visible and hidden, maximized/restored/full-screen states, multiple windows, controls on either side, display scaling, long localized titles, RTL layout, high contrast, keyboard navigation, touch-enabled desktops, and unsupported browsers.

Automate hit testing so native controls and drag regions never cover interactive elements. Verify every application action remains reachable in the fallback standalone layout and that mobile installations ignore the enhancement cleanly.

## Gotchas

- CSS environment variables can resolve differently after a window-state change.
- The API describes available title-bar geometry; it does not guarantee a specific operating-system decoration.
- Drag regions can swallow pointer interaction if their exclusions are incomplete.
- Browser support and install criteria vary, so maintain a current capability matrix.

## Official sources

- [WICG Window Controls Overlay specification](https://wicg.github.io/window-controls-overlay/)
- [W3C Web App Manifest — display_override](https://www.w3.org/TR/appmanifest/#display_override-member)
