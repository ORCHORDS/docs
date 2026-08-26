# Prometheus rule-group limit budget

**Problem**

A recording-rule group can generate excessive series and overwhelm evaluation or storage.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use only after measuring the relevant operational boundary.

## Controls

- Configure the boundary explicitly and preserve required validation.
- Assign ownership, monitoring, and rollback.
- Apply least privilege.

## Implementation

- Canary before fleet rollout.
- Record effective configuration and version.
- Fail closed on unsupported behavior.

## Tests

- Test boundary, failure, restart, concurrency, and rollback cases.
- Verify no required check is skipped.

## Gotchas

- Version support varies.
- Configuration success does not prove runtime correctness.
- Broad scope can increase impact.

## Official sources

- [Official documentation](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/)
