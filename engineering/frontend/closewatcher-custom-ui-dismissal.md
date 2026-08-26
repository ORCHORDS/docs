# CloseWatcher for custom UI dismissal

**Issue:** Custom drawers, pickers, and overlays often listen only for Escape or a click, so they miss platform-specific close requests such as Android back and diverge from native dialog behavior.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented — limited browser availability; progressive enhancement required

## Decision

Prefer native dialog and popover elements where their semantics fit. For a truly custom closable component, progressively enhance with CloseWatcher so platform close requests and the component’s own close control share one lifecycle.

## Controls

- Feature-detect `CloseWatcher`; retain tested keyboard, pointer, and application-navigation fallbacks.
- Create a watcher only while its component is open.
- Route a user-requested, vetoable close through `requestClose()`; use `close()` only when bypassing cancellation is intentional.
- Handle `cancel` for unsaved-state confirmation and `close` for teardown.
- Call `destroy()` when the component disappears by another path.
- Restore focus and accessible state independently; CloseWatcher does not supply full dialog semantics.
- Keep nested overlay ownership explicit because watcher grouping depends on user activation.

## Verification

Test Escape, Android back, the visible close button, application navigation, nested overlays, unsaved-state cancellation, teardown, and repeated open/close cycles. Run the fallback suite in browsers without CloseWatcher and ensure no duplicate close event occurs.

## Gotchas

CloseWatcher is not a focus trap, accessibility role, animation manager, or history router. Multiple watchers created without user activation can be grouped and receive one close request together. Support remains uneven, so it must not be the only dismissal mechanism.

## Sources

- [WHATWG HTML: Close watchers](https://html.spec.whatwg.org/multipage/interaction.html#close-requests-and-close-watchers)
- [MDN CloseWatcher compatibility and API](https://developer.mozilla.org/en-US/docs/Web/API/CloseWatcher)
