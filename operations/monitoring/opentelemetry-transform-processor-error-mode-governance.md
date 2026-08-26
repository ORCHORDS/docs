# OpenTelemetry transform processor error-mode governance

**Issue:** A malformed or type-incompatible telemetry transformation can drop data, flood logs, or silently leave sensitive attributes unchanged depending on error handling.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Set transform statements from reviewed OTTL, choose `error_mode` explicitly per risk, and apply redaction before exporters. Use `propagate` when transformation correctness is required, or `ignore` only with error telemetry and an accepted fallback. Pin Collector component versions.

## Verification

Run golden telemetry through every statement, including missing attributes and wrong types. Assert transformed output, dropped counts, processor errors, and behavior for the chosen error mode before rollout.

## Gotchas

Ignoring errors can preserve unredacted input; propagating errors can drop whole payloads. OTTL function availability and contexts vary by component version.

## Official sources

- https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/transformprocessor
- https://opentelemetry.io/docs/collector/transforming-telemetry/
