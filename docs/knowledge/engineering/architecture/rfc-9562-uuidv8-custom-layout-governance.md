# RFC 9562 UUIDv8 custom-layout governance

**Issue:** UUIDv8 reserves space for application-defined layouts but provides no interoperability by itself.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Publish bit layout/version, randomness/privacy model and collision budget; keep parser strict.

## Tests

Cross-language vectors, malformed variant/version, collision simulation, migration tests.

## Gotchas

UUIDv8 is not automatically sortable, secure, or globally meaningful.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9562
