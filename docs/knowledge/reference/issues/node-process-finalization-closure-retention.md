# Node process finalization closure retention

**Issue:** Node process.finalization callbacks can accidentally close over the tracked object and prevent collection; callbacks are not guaranteed.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Use top-level non-capturing callbacks, explicit disposal first, unregister after disposal, pin API stability.

## Tests

Force normal exit, beforeExit, GC opportunity, abrupt termination and retained closure.

## Gotchas

Finalization is backup observability, never critical cleanup.

## Official sources

- https://nodejs.org/api/process.html#processfinalizationregisterref-callback
