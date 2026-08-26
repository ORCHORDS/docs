# JSON:API atomic operations transaction contract

**Issue:** Treating a JSON:API Atomic Operations document as an ordinary list of independent requests breaks the extension’s all-or-nothing guarantee and can leave related resources partially changed.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Negotiate the Atomic Operations extension through the JSON:API media type `ext` parameter and reject unsupported extension requests.
- Accept the top-level `atomic:operations` member only in the ordered form defined by the extension.
- Execute operations in document order inside one atomic boundary: either every operation succeeds or none of their effects persist.
- Resolve a local identifier (`lid`) only within the submitted document and never promote it to a durable authorization identifier.
- Authorize every operation and relationship mutation independently even though persistence is atomic.
- Bound operation count, payload size, relationship fan-out, and transaction duration.

## Implementation and tests

Parse and validate the complete document before opening the write transaction where practical. Maintain a request-local `lid` table, execute the ordered operations, and build `atomic:results` in corresponding order. Roll back on validation, authorization, conflict, storage, or result-construction failure.

Test mixed add, update, remove, and relationship operations; forward and invalid local references; a failure at every position; retry after an ambiguous transport failure; and concurrent writes. After each injected failure, assert that no operation effect remains.

## Gotchas and applicability

Atomicity is not idempotency. A client retry after losing the response can repeat a committed mutation unless the application adds a replay-safe request key and durable outcome record. Database rollback cannot undo email, queue, webhook, or external-service side effects; stage those through an outbox or compensating design.

This article applies only when the JSON:API Atomic Operations extension is negotiated. It does not change ordinary JSON:API update semantics.

## Official sources

- [JSON:API Atomic Operations extension](https://jsonapi.org/ext/atomic/)
- [JSON:API specification: content negotiation](https://jsonapi.org/format/#content-negotiation)
