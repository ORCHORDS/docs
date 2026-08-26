# Focus indication must survive mixed-input adaptation

**Issue**

Interfaces that hide focus rings after pointer use can fail when a person immediately switches to keyboard or synthetic activation. Input adaptation must preserve visible programmatic focus.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use native focus semantics and `:focus-visible`; never globally remove outlines or persist a “mouse user” state.
- Provide fallback and forced-colors focus styles.
- Move focus only for a documented interaction transition; responsive layout changes must not reset it.
- Keep focus appearance independent of hover and coarse/fine pointer styling.
- Implement the relevant keyboard pattern for custom widgets.

## Verification

1. Alternate mouse, touch, keyboard, and programmatic focus without reload.
2. Resize navigation while focus is inside and preserve the logical target.
3. Test forced colors, zoom, sticky overlays, dialogs, and focus restoration.
4. Assert visible focus and meaningful focus order for every action.

## Gotchas

- `:focus-visible` is a user-agent heuristic, not last-device storage.
- Programmatic focus may need an indicator after pointer activation.
- A CSS outline can still be clipped, covered, or indistinguishable.
- Hover is not a focus substitute.

## Official sources

- [WCAG Focus Visible](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html)
- [WCAG Focus Appearance](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html)
- [Selectors Level 4 focus-visible](https://www.w3.org/TR/selectors-4/#the-focus-visible-pseudo)
