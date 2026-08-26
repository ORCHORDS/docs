# OpenTelemetry configuration-provider trust boundary

**Problem**

Collector configuration can be assembled from environment, files, HTTP, YAML, and other providers, expanding the configuration supply chain.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when Collector config resolves external URIs or substitutions.

## Controls

- Allowlist provider schemes and endpoints.
- Keep secrets in dedicated providers and out of rendered logs.
- Pin resolver behavior and bound network fetches.

## Implementation

- Resolve into a protected effective config.
- Validate before rollout and record non-secret digests.
- Fail closed on missing values.

## Tests

- Test unknown schemes, cycles, timeout, redirects, malformed content, and secret redaction.

## Gotchas

- Provider availability can block startup.
- Environment substitution can leak or truncate values.
- Merged precedence changes behavior.

## Official sources

- [Official documentation](https://opentelemetry.io/docs/collector/configuration/)
