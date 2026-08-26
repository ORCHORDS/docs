# microservices-vs-monolith

**Issue:** Choosing the right decomposition strategy for a given team and product stage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams adopt microservices for greenfield projects and spend 80% of time on infrastructure instead of product.

## Pattern / Solution
Decision matrix:

| Factor | Monolith | Microservices |
|--------|----------|---------------|
| Team size | < 10 | > 20 per service |
| Deploy cadence | Low | High, independent |
| Domain clarity | Fuzzy | Well-defined |
| Data coupling | High | Low |
| Org Conway | Single | Multi-team |

Start monolith, extract services when: independent scaling is needed, team owns a clear bounded context, or deploy frequency diverges.

```
Monolith:  [UI → Service Layer → DB]
Microservices: [UI] → [API GW] → [Svc A → DB-A]
                                → [Svc B → DB-B]
```

## Gotchas
- Distributed monolith: services coupled at DB or deploy level — worst of both worlds
- Network calls replace in-process calls; latency and failure modes multiply
- Shared libraries become coupling vectors; prefer data contracts over shared code

## Related
- `modular-monolith-pattern.md`
- `strangler-fig-migration.md`
- `domain-driven-design-basics.md`
