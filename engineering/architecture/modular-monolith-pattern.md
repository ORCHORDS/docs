# modular-monolith-pattern

**Issue:** Achieving team autonomy and clear boundaries without distributed systems complexity
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Team wants independent modules but is not ready for microservices operational overhead.

## Pattern / Solution
A modular monolith enforces module boundaries at the code level while deploying as a single unit.

```
src/
  modules/
    orders/
      api/       ← public interface only
      internal/  ← private implementation
      db/        ← module-owned schema
    inventory/
      api/
      internal/
      db/
  shared/
    events/      ← typed domain events
```

Rules:
- Cross-module calls only via public API or events, never internal packages
- Each module owns its DB schema (separate schema prefix or tables)
- Linting enforces import boundaries

## Gotchas
- Without tooling enforcement, boundaries erode quickly
- Shared DB transactions across modules re-introduce coupling
- Extraction to microservices later is simpler if module boundaries were clean

## Related
- `microservices-vs-monolith.md`
- `strangler-fig-migration.md`
- `bounded-context-design.md`
