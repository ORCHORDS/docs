# JSON Schema dynamicRef resolution boundary

**Issue:** JSON Schema dynamic references resolve through dynamic scope, so bundling or changing anchors can alter validation without changing an instance.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Pin dialect and schema graph, make dynamic anchors unique by intent, bundle immutably, validate resolver/URI policy.

## Tests

Nested overrides, duplicate anchors, offline bundle, moved schema, unsupported dialect, recursive data.

## Gotchas

dynamicRef is not ordinary static ref; different validators may expose unsupported-dialect failures differently.

## Official sources

- https://json-schema.org/draft/2020-12/json-schema-core
