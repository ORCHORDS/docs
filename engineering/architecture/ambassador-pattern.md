# ambassador-pattern

**Issue:** Offloading common network connectivity tasks from the application to a proxy
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Every service must implement retry logic, connection pooling, and circuit breaking to call external services.

## Pattern / Solution
The ambassador acts as an out-of-process proxy to the external service, handling cross-cutting concerns.

```
[Application] → [Ambassador Proxy] → [External Service / Database]
                    - Connection pooling
                    - Retry with backoff
                    - Circuit breaking
                    - Logging
                    - Health checking
```

Example: Envoy as ambassador to a remote database, handling connection reuse and failover.

Difference from sidecar: sidecar handles inbound/outbound traffic for the service; ambassador specifically proxies a specific external dependency.

## Gotchas
- Adds a network hop; latency impact must be measured
- Ambassador configuration must be kept in sync with dependency changes
- Not all SDKs support transparent proxy routing; may need explicit configuration

## Related
- `sidecar-pattern.md`
- `circuit-breaker-design.md`
- `service-mesh-patterns.md`
