# Adaptive navigation chrome needs information-architecture parity

**Issue:** A mobile bottom bar and desktop sidebar expose different primary destinations or reorder them without a product reason, making the application feel like two unrelated structures.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Lesson

Bottom tabs and sidebars are two projections of one information architecture. Preserve destination set, naming, ordering logic, active-state meaning, and landmark relationships; move only what the available space requires.

**Sources:** [WCAG 2.2 consistent navigation](https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation.html) · [WCAG 2.2 info and relationships](https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html) · [WAI-ARIA navigation landmark](https://www.w3.org/WAI/ARIA/apg/patterns/landmarks/examples/navigation.html)

## Apply

- define primary, secondary, contextual, and account destinations before choosing chrome;
- keep primary items and labels consistent across shells;
- expose each navigation region with a distinct accessible label;
- preserve DOM reading/focus order independently of visual rearrangement;
- put secondary items behind a clearly named disclosure only when necessary;
- avoid cloning simultaneously focusable mobile and desktop navigation trees.

## Verify

Compare route inventories at every supported width, zoom level, orientation, and text expansion. Test screen-reader landmark lists, keyboard order, active indication, localization, and viewport changes. Every primary task must remain reachable without switching modes.

## Gotchas

A sidebar can hold more items, but capacity does not make them primary. CSS-hidden duplicate navigation can remain confusing to assistive technology if not truly removed from interaction. Icons alone are not stable names.
