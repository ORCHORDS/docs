# sidecar-pattern

**Issue:** Adding capabilities to a service without modifying its code by co-deploying a helper process
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Logging, metrics, and proxy logic need to be added to legacy services that cannot be modified.

## Pattern / Solution
A sidecar is a separate container/process deployed alongside the main application, sharing network namespace.

```
Pod:
  ┌────────────────────────────────────┐
  │ [Main App Container]               │
  │   localhost:8080                   │
  │                                    │
  │ [Sidecar Container]                │
  │   - Envoy proxy (traffic)          │
  │   - Filebeat (log shipping)        │
  │   - Vault agent (secret injection) │
  └────────────────────────────────────┘
```

Use cases: service mesh proxy, log forwarder, config sync, secrets injection, health check proxy.

## Gotchas
- Sidecar lifecycle must match the main container; init containers handle startup ordering
- Resource limits for sidecar count against pod limits; account for them
- Too many sidecars per pod create operational complexity

## Related
- `service-mesh-patterns.md`
- `ambassador-pattern.md`
- `secret-management-architecture.md`
