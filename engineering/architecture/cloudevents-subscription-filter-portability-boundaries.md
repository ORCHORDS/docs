# CloudEvents subscription filter portability boundaries

**Issue:** Event-routing filters that look equivalent across brokers can differ in case sensitivity, missing-attribute behavior, nesting, and error handling, causing silent over-delivery or data loss.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Status and decision

CloudEvents core specification 1.0.2 and CESQL 1.0.0 are released, while the CloudEvents Subscriptions specification is listed as working draft. Use the draft only behind an internal versioned abstraction and do not claim released-standard conformance.

## Controls

- Pin the exact subscription-spec commit/version used by producer, manager, and tests.
- Require supported dialect discovery and reject unsupported dialects.
- Treat top-level filter expressions as AND: if any evaluates false, the event is not delivered.
- Test required draft dialects (`exact`, `prefix`, `suffix`, `all`, `any`, `not`) and treat SQL as optional.
- Validate filters at creation/update; never silently ignore unknown dialects.
- Authorize the sink independently from filter evaluation.
- Define dead-letter, retry, audit, and deletion behavior outside filtering.
- Preserve source events so routing changes can be replayed safely.

## Verification

Use a shared conformance corpus covering missing attributes, empty values, case differences, Unicode, nested Boolean filters, invalid dialects, and changed event schemas. Compare intended and observed delivery counts.

## Gotchas

A filter is not an authorization boundary. Draft semantics can change. Absence or an empty filter means true in the draft. SQL errors evaluate false, which can silently suppress delivery unless monitored.

## Sources

- [CloudEvents specification repository and release table](https://github.com/cloudevents/spec)
- [CloudEvents Subscriptions working draft](https://github.com/cloudevents/spec/blob/main/subscriptions/spec.md)
