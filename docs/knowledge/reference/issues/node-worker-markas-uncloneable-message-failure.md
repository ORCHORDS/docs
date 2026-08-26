# Node worker markAsUncloneable message failure

**Issue:** Objects marked uncloneable cause DataCloneError when sent through worker messaging, which can surface far from the mark site.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Mark only owned internal objects, expose serializable DTOs, validate message boundary and handle postMessage failure.

## Tests

Nested marked object, transfer list, MessagePort, workerData, retry, third-party object.

## Gotchas

The marker is process-local policy and does not sanitize or freeze data.

## Official sources

- https://nodejs.org/api/worker_threads.html#workermarkasuncloneableobject
