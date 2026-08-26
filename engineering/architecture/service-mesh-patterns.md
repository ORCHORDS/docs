# service-mesh-patterns

**Issue:** Managing service-to-service communication, observability, and security without modifying application code
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Every service re-implements retries, circuit breakers, mTLS, and distributed tracing; inconsistently.

## Pattern / Solution
A service mesh injects a sidecar proxy into each service pod; all traffic flows through the proxy.

```
[Service A] → [Sidecar A] ──mTLS──→ [Sidecar B] → [Service B]
                   ↑                       ↑
                [Control Plane: Isito/Linkerd/Consul Connect]
                   - Certificates
                   - Traffic policies
                   - Telemetry
```

Features provided by mesh: mTLS, retries, circuit breaking, canary traffic splitting, distributed tracing, metrics.

Products: Istio, Linkerd, Consul Connect, AWS App Mesh.

## Gotchas
- Sidecar adds latency (1-2ms per hop); measure before and after
- Control plane is complex; operators need deep expertise
- Linkerd is simpler than Istio; choose based on feature needs

## Related
- `sidecar-pattern.md`
- `circuit-breaker-design.md`
- `zero-trust-architecture.md`
