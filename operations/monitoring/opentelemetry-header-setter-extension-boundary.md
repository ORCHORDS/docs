# OpenTelemetry header-setter extension boundary

**Problem**

Dynamic header injection can propagate credentials or tenant identity across exporters and redirect boundaries.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when outbound Collector clients need context-derived or secret-backed headers.

## Controls

- Allowlist header names and sources.
- Never derive authorization from untrusted telemetry attributes.
- Scope credentials per endpoint.

## Implementation

- Enable the extension only for intended clients.
- Use secret providers and redact effective config.
- Restrict redirects/proxies.

## Tests

- Test missing context, tenant collision, expiry, redirect, exporter retry, and log redaction.

## Gotchas

- Headers can cross trust boundaries.
- Cardinality/context propagation differs by signal.
- Extension support varies by distribution.

## Official sources

- [Official documentation](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/headerssetterextension)
