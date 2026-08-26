# virtual-keyboard-viewport-handling

**Issue:** On mobile, opening the on-screen keyboard is the moment chat apps, login screens, and messaging UIs break: sticky input bars vanish under the keyboard, focused fields scroll out of view, and fixed/absolute-positioned toolbars jump or flicker. The root cause is that mobile browsers maintain two viewports — the layout viewport and the visual viewport — and keyboards resize or overlay them differently per browser and per OS. Web developers have three partially-overlapping mechanisms to cope: the visualViewport API (universal), the Chromium-only VirtualKeyboard API (geometrychange plus keyboard-inset-* CSS environment variables), and the meta viewport interactive-widget keyword (also Chromium-only as of 2025). Safari and Firefox support neither of the newer mechanisms (tracked in WebKit bug 230225 and WPT Interop issue #<number>), so production code needs layered feature detection and fallbacks.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Two-Viewports Problem

1. **Layout viewport vs visual viewport.** The layout viewport is what CSS layout and 100vh/100dvh resolve against; the visual viewport is the currently visible portion, which shrinks when a keyboard appears (or stays the same when the keyboard overlays). Ahmad Shadeed's Virtual Keyboard API write-up frames the entire problem this way: most keyboard bugs are a mismatch between which viewport your positioning assumed and which one the browser actually resized.

2. **Position: fixed follows neither consistently.** Elements positioned fixed relative to the layout viewport can end up under the keyboard (when only the visual viewport shrank) or jumping mid-animation (when the browser temporarily resizes then restores). Never rely on fixed positioning alone to keep a composer bar visible; it works on some browser/OS combinations and fails on others.

3. **Prefer dynamic viewport units.** Use 100dvh (dynamic viewport height) instead of 100vh for full-height app shells: 100vh is frozen to the largest viewport on many mobile browsers and guarantees off-screen content under the keyboard, while 100dvh tracks keyboard show/hide. Pair it with min-height so desktop layout is unaffected.

## The VirtualKeyboard API (Chromium)

1. **Opt in with virtual-keyboard-overlays-content.** Setting the CSS property virtual-keyboard-overlays-content: auto (or navigator.virtualKeyboard.overlaysContent = true) tells the browser to stop auto-resizing, giving you the keyboard geometry instead. This is the foundation of the Chrome Developers "full control with the VirtualKeyboard API" pattern.

2. **React to geometrychange.** Listen to navigator.virtualKeyboard.addEventListener('geometrychange', ...) to receive the keyboard's bounding rect as often as it changes (keyboards animate open). Use the event to set padding/translate on your composer bar or scroll container so the UI tracks the keyboard's animation instead of snapping after it.

3. **Use the keyboard-inset-* CSS environment variables.** env(keyboard-inset-height), keyboard-inset-top, keyboard-inset-width, and keyboard-inset-bottom expose the keyboard rect to pure CSS, so a sticky composer can be styled with padding-bottom: env(keyboard-inset-height, 0px) with a graceful zero fallback. CSS-first means no JS layout pass and no flash of misplaced UI.

4. **Remember it is Chromium-only.** As of 2025 the VirtualKeyboard API ships only in Chromium browsers; Safari and Firefox have not implemented it (WebKit bug 230225 remains open). Guard every access (if ('virtualKeyboard' in navigator)) and pair with the fallbacks below — this is the same progressive-enhancement posture as the VirtualKeyboard-less majority of users on iOS.

## The interactive-widget Meta Viewport Keyword

1. **Set the resize behavior explicitly.** The viewport meta tag accepts interactive-widget with three values: resizes-visual (default; only the visual viewport shrinks), resizes-content (the layout viewport resizes, so layout itself reflows above the keyboard), and overlays-content (nothing resizes; you get no free adjustment at all). The HTMHell advent calendar piece on interactive-widget covers the trade-offs in depth.

2. **resizes-content for app-like layouts.** For chat and full-screen form apps, interactive-widget=resizes-content is often the right call: flex/grid layouts naturally compress, fixed elements move up with the layout viewport, and you may need no JavaScript at all. The cost is a full reflow (potential CLS during the keyboard animation) and that it is currently Chromium-only.

3. **overlays-content pairs with the VirtualKeyboard API.** If you are already handling geometry yourself via geometrychange or the env variables, overlays-content prevents the browser's automatic resize from fighting yours. Combining default auto-resize with your own transforms is the classic source of double-adjusted, twice-tucked input bars.

## Cross-Browser Fallbacks

1. **Use the visualViewport API as the universal baseline.** window.visualViewport exposes height, offsetTop, and resize/scroll events on all modern mobile browsers. Compute the visible height as (vv.height + vv.offsetTop) and apply it as a CSS custom property (--app-visible-height) that your composer bar and scroll containers consume. This is the only mechanism that works on iOS Safari and Firefox today.

2. **Scroll the focused element into view manually.** element.scrollIntoView({ block: 'nearest' }) after focus (and again after orientation or keyboard geometry changes) compensates for browsers that scroll the visual viewport unpredictably. Do it in a rAF after the geometry event settles to avoid fighting the browser's own scroll correction.

3. **Debounce and animate geometry changes.** Keyboard open/close fires many resize events during its animation; coalesce them (rAF or ~50 ms debounce) before committing layout, and transition your composer's transform so it visibly tracks the keyboard rather than stuttering. Never trigger data fetching or heavy renders from geometry events.

## Sticky Composer Bars and Chat UX

1. **Structure the DOM so the composer sits above the scroll area.** A flex column with a flex-1 scroll region and a composer sibling (not position: fixed) survives every keyboard mode: when the layout viewport resizes, the column compresses and the composer stays attached without any JS. Reserve fixed positioning for when you must overlay.

2. **Keep the caret visible during typing growth.** As message text grows to multiple lines, the composer grows and shrinks the scroll region; re-scroll the thread bottom (and the caret into view) on composer resize, capped at a max-height with internal scroll on the textarea itself.

3. **Test on real iOS and Android, not emulation.** Keyboard behavior differs across iOS Safari (visual-viewport-only), Android Chrome (all three mechanisms), and in-app webviews ( Capacitor/WebView), and none of it is faithfully emulated on desktop. Verify: focus first field, type, rotate with keyboard open, dismiss via scroll-to-dismiss, and voice-keyboard input — each path produces different geometry events.
