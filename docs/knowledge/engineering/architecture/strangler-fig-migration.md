# strangler-fig-migration

**Issue:** Safely migrating a legacy monolith to new architecture without big-bang rewrites
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Big-bang rewrites fail 70% of the time. The legacy system must stay live while migration proceeds.

## Pattern / Solution
Named after the strangler fig tree that grows around a host and eventually replaces it.

```
Phase 1: Proxy in front of legacy
  Client → [Facade/Proxy] → [Legacy Monolith]

Phase 2: Route new functionality to new service
  Client → [Facade/Proxy] → [New Service] (new paths)
                          → [Legacy Monolith] (old paths)

Phase 3: Migrate old paths incrementally
  Client → [Facade/Proxy] → [New Service] (all paths)
  Legacy decommissioned
```

Steps: add facade → intercept one endpoint → reimplement → redirect → repeat → remove legacy.

## Gotchas
- The facade becomes a bottleneck; keep it thin (proxy only, no business logic)
- Data migration is harder than code migration; run dual-writes during transition
- Integration tests must cover both old and new paths during transition

## Related
- `microservices-vs-monolith.md`
- `anti-corruption-layer.md`
- `outbox-pattern.md`
