# CSS interactivity property boundaries

**Issue:** A UI disables a visual subtree with opacity or pointer-events while descendants remain keyboard-focusable, editable, or exposed to assistive technology.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** experimental/newer CSS; retain HTML inert fallback

CSS UI defines an `interactivity` property, including an inert state. Treat it as progressive enhancement around a state model that uses established HTML semantics and restores focus deliberately.

**Source:** [CSS Basic User Interface Level 4 — interactivity](https://drafts.csswg.org/css-ui-4/#inertness)

## Controls

- prefer native disabled states for individual form controls;
- use HTML `inert` as the interoperable subtree baseline;
- never use visual suppression as authorization;
- store and restore focus outside newly inert content;
- remove inertness atomically with visible enablement.

## Verification

Test pointer, keyboard, programmatic focus, screen readers, find-in-page, selection, editing, nested inert regions, unsupported engines, and state reversal.

## Gotchas

CSS support and exact behavior are evolving. `pointer-events: none` is not equivalent. Inert content remains in DOM and accessible to scripts.
