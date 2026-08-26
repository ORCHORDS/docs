# RFC 9205 HTTP protocol semantics contract

**Issue:** Application protocols built on HTTP can accidentally redefine methods/statuses or misuse transport state as application state.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Map safe/idempotent semantics honestly, use registered statuses/fields, define redirects/caching/auth and intermediaries before deployment.

## Tests

Retry, redirect, cache, proxy transformation, unknown status, HTTP version changes.

## Gotchas

HTTPS does not fix an application protocol that lies about method semantics.

## Official sources

- https://www.rfc-editor.org/rfc/rfc9205
