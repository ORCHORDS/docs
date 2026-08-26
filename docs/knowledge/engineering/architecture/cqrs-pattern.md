# cqrs-pattern

**Issue:** Separating read and write models to optimize each independently
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Complex read requirements (joins, aggregations) pollute write models; a single model cannot be optimal for both.

## Pattern / Solution
Command Query Responsibility Segregation: writes go to command model; reads go to query model.

```
                    ┌─────────────┐
Command → Write Side│  Command    │→ DB (normalized)
                    │  Handlers   │→ Emit events
                    └─────────────┘
                          │ events
                          ↓
                    ┌─────────────┐
Query  ← Read Side  │  Projections│← Denormalized read store
                    │  (views)    │   (Elasticsearch, Redis, PG materialized view)
                    └─────────────┘
```

Simple CQRS: same DB, separate models (low complexity). Full CQRS: separate stores, eventual consistency between write and read.

## Gotchas
- Read-side is eventually consistent; UIs must handle "processing" states
- Projections must be rebuildable from the event log
- Do not apply CQRS to every feature; start with read-heavy or complex query scenarios

## Related
- `event-sourcing-pattern.md`
- `vertical-slice-architecture.md`
- `read-through-cache.md`
