# RFC 9557 critical time-zone suffix contract

**Issue:** RFC 9557 extends Internet timestamps with zone/calendar suffixes and a critical flag.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Parse RFC3339 base, preserve suffixes, reject unknown/inconsistent critical tags, pin TZDB.

## Tests

Test DST gaps/folds, Z plus zone, duplicate tags, unknown elective/critical tags.

## Gotchas

A zone name is not an instant; elective unknown tags may be ignored.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9557
