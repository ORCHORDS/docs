# OpenAPI discriminator mapping resolution contract

**Issue:** OpenAPI discriminators can select a schema by property value, with explicit mappings or implicit schema-name lookup. Ambiguous or stale mappings make validators, generators, and clients choose different variants.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented; OpenAPI 3.1.1 released

## Controls and implementation

Use explicit mapping URIs for every supported value; keep discriminator property required where the contract depends on it; version semantic changes; validate mapping targets and JSON Schema composition; define unknown-value behavior.

## Tests

Exercise every value, unknown/case-variant values, missing property, overlapping oneOf schemas, renamed components, external references, and generator/runtime parity.

## Gotchas

A discriminator is a selection hint, not a substitute for schema validation. Implicit mapping depends on schema names and can break on harmless-looking refactors.

## Official sources

- https://spec.openapis.org/oas/v3.1.1.html#discriminator-object
