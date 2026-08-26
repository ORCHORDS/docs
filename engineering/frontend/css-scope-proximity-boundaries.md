# CSS @scope proximity and boundary controls

**Issue:** Component styles rely on naming conventions or deep selectors, then leak into nested components or lose precedence when markup is composed.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** progressive enhancement; verify support

CSS Scoping defines `@scope` with a scoping root and optional limit. Use it to constrain selector matching, while keeping cascade layers and specificity policy explicit.

**Source:** [CSS Scoping Module Level 1](https://drafts.csswg.org/css-scoping-1/#scope-atrule)

## Controls

- choose stable semantic roots and limits;
- avoid selectors whose meaning depends on accidental nesting distance;
- combine with cascade layers rather than escalating specificity;
- keep a safe fallback for browsers without support;
- document whether nested components inherit or form a scope limit.

## Verification

Test nested instances, slotted/generated content, reordered markup, fallback browsers, themes, and conflicting rules at equal specificity. Confirm scoped styles neither escape nor disappear at the intended limit.

## Gotchas

`@scope` is a cascade/matching boundary, not DOM encapsulation or security. Scope proximity can affect conflict resolution. Shadow DOM and `@scope` solve different problems.
