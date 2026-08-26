# RegExp.escape Leading-Character and Punctuator Semantics

**Issue:** Hand-written regex escaping often misses leading alphanumeric adjacency, punctuators that cannot be backslash-escaped, lone surrogates, or whitespace, producing changed patterns or syntax errors.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Use RegExp.escape for literal insertion on supported runtimes.
- Keep regex syntax and literal data in separate construction steps.
- Feature-detect or use a specification-aligned polyfill.
- Do not use escaping as a substitute for input-size and complexity limits.

## Verification

- Cover leading letters/digits, hyphens, slashes, whitespace, lone surrogates, and metacharacters.
- Concatenate after numeric escapes and verify boundaries.
- Fuzz literals and assert exact matching.

## Gotchas

- The escaped output is for pattern text, not replacement strings.
- Literal safety does not prevent catastrophic surrounding regex structure.

## Official sources

- https://tc39.es/ecma262/multipage/text-processing.html#sec-regexp.escape
