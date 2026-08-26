# HTML search landmark semantics

**Issue:** A site wraps every filtering input in generic containers or labels multiple unrelated regions “search,” making landmark navigation noisy and ambiguous.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented with fallback semantics

The HTML `search` element represents a section containing controls for search or filtering. Use it for a meaningful search region, with a distinct accessible name when multiple search landmarks exist.

**Source:** [WHATWG HTML — the search element](https://html.spec.whatwg.org/multipage/grouping-content.html#the-search-element)

## Controls

- include an actual form/controls with proper labels;
- name multiple search regions by purpose;
- retain native form submission and keyboard behavior;
- use `role="search"` fallback only where needed, without redundant conflicting roles;
- do not use search as a styling wrapper.

## Verification

Test landmark lists, accessible names, keyboard submit/reset, validation, no-JavaScript submission, multiple regions, localization, and unsupported assistive/browser combinations.

## Gotchas

Search landmark semantics do not label the input itself. Site search, filtering, and find-in-page are different tasks. Too many landmarks reduce rather than improve navigation.
