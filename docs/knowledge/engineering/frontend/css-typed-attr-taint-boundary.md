# CSS typed attr() taint boundary

**Issue:** Modern CSS drafts allow typed `attr()` values beyond strings. Treating untrusted attributes as arbitrary URLs, dimensions, or executable styling can create layout abuse and unsafe assumptions.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** experimental

## Controls and implementation

Allowlist attributes and expected types, provide a valid fallback, clamp numeric ranges, and keep URL/security decisions outside CSS. Use feature detection and a conventional declaration first. Attribute-derived values remain presentation input, not trusted application state.

## Verification

Test missing/malformed attributes, wrong units, huge/negative values, inheritance, custom properties, unsupported browsers, and invalid-at-computed-value behavior.

## Gotchas

`attr()` values can be tainted and restrictions differ by property; successful parsing is not authorization.

## Sources

- W3C CSSWG, [CSS Values and Units Level 5 — attr()](https://www.w3.org/TR/css-values-5/#attr-notation)
