# Helm Kubernetes-client QPS and burst budget

**Problem**

Helm can overload an API server or time out when client throttling is mismatched to chart size and cluster policy.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for large releases only after measuring API demand and server capacity.

## Controls

- Set `--qps` and `--burst-limit` together from evidence.
- Preserve server admission, priority, timeout, atomic mode, and required checks.
- Budget aggregate concurrency across releases.

## Implementation

- Canary one release and observe client throttling and API latency.
- Optimize hooks and object churn before raising limits.
- Keep a rollback configuration.

## Tests

- Test cold install, no-op upgrade, rollback, throttling, and concurrent releases.
- Verify failure classification and atomic rollback.

## Gotchas

- Client limits do not grant server capacity.
- Higher burst can harm controllers.
- Rate-limit and timeout failures differ.

## Official sources

- [Helm upgrade](https://helm.sh/docs/helm/helm_upgrade/)
