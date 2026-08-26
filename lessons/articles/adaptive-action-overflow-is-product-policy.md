# Adaptive action overflow is product policy

**Issue:** When space shrinks, actions disappear according to CSS order or implementation convenience, hiding frequent or safety-critical work in an unlabeled overflow menu.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Lesson

Define action priority and overflow behavior as product policy. Keep the primary action visible, retain essential safety/recovery actions, and move lower-priority actions into one predictable, accessible disclosure without changing their semantics.

**Sources:** [WCAG 2.2 focus order](https://www.w3.org/WAI/WCAG22/Understanding/focus-order.html) · [WCAG 2.2 target size minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) · [WAI-ARIA menu button pattern](https://www.w3.org/WAI/ARIA/apg/patterns/menu-button/)

## Apply

- classify actions as primary, frequent, contextual, destructive, or rare;
- keep labels where ambiguity would remain with icons;
- use a named disclosure button with expanded state and predictable focus return;
- preserve authorization, confirmation, keyboard shortcuts, and telemetry when an action moves;
- reserve enough target spacing instead of shrinking controls below usability;
- never make hover the only way to discover overflowed actions.

## Verify

Test every action at narrow widths, 200% and 400% zoom, long translations, coarse pointer, keyboard, touch, screen reader, and reduced motion. Opening, selecting, dismissing, and returning focus must follow the same task contract.

## Gotchas

“More” is navigation only if its contents are destinations; otherwise it is an action disclosure. Moving destructive actions can invalidate muscle memory, so keep placement and confirmation deliberate. Usage telemetry does not override accessibility or recovery needs.
