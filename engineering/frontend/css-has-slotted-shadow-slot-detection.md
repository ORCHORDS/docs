# CSS :has-slotted shadow-slot detection

**Issue:** A web component uses JavaScript mutation checks only to style an empty versus populated slot, creating timing and fallback inconsistencies.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** experimental/newer selector; feature-detect

CSS Scoping defines `:has-slotted` for matching a slot that has slotted content. Use it as progressive presentation logic; component correctness and accessible fallback content must not depend on selector support.

**Source:** [CSS Scoping Module Level 1 — :has-slotted](https://drafts.csswg.org/css-scoping-1/#has-slotted-pseudo)

## Controls

- keep default slot fallback meaningful;
- feature-detect selector support and provide baseline styling;
- distinguish assigned nodes from meaningful non-whitespace content in application logic when needed;
- avoid duplicating MutationObserver and CSS behavior;
- retain accessible names independent of visual empty state.

## Verification

Test no assignment, text/whitespace, element nodes, reassignment, nested slots, fallback content, unsupported browsers, and dynamic removal. Confirm state changes do not flash or leave stale affordances.

## Gotchas

The selector matches slot assignment semantics, not business-valid content. Draft behavior/support can change. It does not cross arbitrary shadow boundaries.
