# CSS sibling-index and sibling-count progressive staggering

**Issue:** Authors often inject per-item inline indices solely to stagger styles. CSS Values Level 5 proposes numeric tree-counting functions, but relying on draft syntax can erase styling in unsupported browsers.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** experimental Working Draft — progressive enhancement only

## Decision

Keep a complete baseline style and use `sibling-index()` or `sibling-count()` only inside a guarded enhancement for decorative calculations. Never use them to encode business identity, semantic order, or accessibility state.

## Controls

- Gate with `@supports` for the exact property/value combination.
- Keep duration and delay caps independent of list length.
- Honor `prefers-reduced-motion`.
- Remember the functions use the flat tree and are one-indexed.
- Ensure dynamic insertion/removal cannot trigger disruptive animation storms.
- Do not expose item count as an authorization or data-loading control.
- Keep source order logical and stable.
- Track specification and browser changes before widening rollout.

## Verification

Test zero, one, many, dynamically reordered, slotted, and pseudo-element cases; reduced motion; unsupported browsers; and very large sibling sets. Confirm the baseline renders correctly when the entire enhanced declaration is dropped.

## Gotchas

CSS Values Level 5 explicitly describes early exploration and expected breaking changes. Flat-tree indexing can differ from naive DOM-child assumptions. A decorative index is not a durable application identifier.

## Sources

- [W3C CSS Values Level 5: Tree Counting Functions](https://www.w3.org/TR/css-values-5/#tree-counting)
- [CSS Working Group Values Level 5 announcement](https://www.w3.org/blog/CSS/2024/09/13/css-values-5-fpwd/)
