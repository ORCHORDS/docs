# CSS reading-flow accessibility boundary

**Issue:** Dense grid and reversed flex layouts can make visual order diverge from sequential keyboard and speech order. CSS Display Level 4 proposes reading-flow controls, but using them casually can hide a broken source structure.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** experimental draft — progressive enhancement only

## Decision

Keep the DOM in the most fundamental logical order. Evaluate `reading-flow` and `reading-order` only for responsive layouts whose meaningful reading order truly changes with presentation, behind compatibility checks and assistive-technology testing.

## Controls

- Do not use the properties to repair arbitrary source-order mistakes.
- Keep headings, labels, descriptions, and controls structurally associated in the DOM.
- Apply `reading-order` only to direct eligible children of a reading-flow container.
- Treat focus order, speech order, visual order, and painting order as separate test dimensions.
- Avoid positive `tabindex` as a competing reordering mechanism.
- Feature-detect support and retain a coherent DOM-order baseline.
- Review every media-query-specific reading flow.
- Mark the implementation experimental with a kill switch.

## Verification

Test keyboard traversal and major screen readers across grid/flex variants, writing modes, zoom, narrow/wide media queries, unsupported browsers, and dynamic insertion. Confirm visual indicators follow focus and DOM order remains understandable with CSS disabled.

## Gotchas

CSS Display Level 4 is a Working Draft and may change. `reading-flow` affects sequential navigation/speech order, not visual layout. Browser support does not guarantee identical assistive-technology behavior.

## Sources

- [W3C CSS Display Module Level 4: Reading Order](https://www.w3.org/TR/css-display-4/#reading-order)
- [CSS Working Group Editor’s Draft](https://drafts.csswg.org/css-display-4/#reading-order)
