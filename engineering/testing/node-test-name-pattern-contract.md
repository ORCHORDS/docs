# Node test-name pattern contract

**Problem**

Regex-based test selection can unintentionally omit required cases when names, escaping, or nested suite prefixes change.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for focused diagnostic lanes, not as the sole authoritative suite unless selection is proven.

## Controls

- Keep the full unfiltered suite required.
- Anchor and escape patterns deliberately.
- Assert selected and skipped counts.

## Implementation

- Pass patterns as separate CLI arguments without shell reinterpretation.
- Publish the resolved test list with results.
- Version named suites as an interface.

## Tests

- Test metacharacters, Unicode, nested names, duplicate names, and zero matches.
- Rename a test and require the focused-lane contract to detect drift.

## Gotchas

- Patterns are regular expressions.
- Matching ancestors can affect descendants.
- A clean filtered run says nothing about omitted tests.

## Official sources

- [Official documentation](https://nodejs.org/api/test.html#filtering-tests-by-name)
