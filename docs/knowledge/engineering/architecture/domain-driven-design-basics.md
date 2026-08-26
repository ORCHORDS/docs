# domain-driven-design-basics

**Issue:** Aligning software structure with business domain concepts to reduce translation cost
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Technical models drift from business reality; developers and domain experts speak different languages.

## Pattern / Solution
DDD establishes a Ubiquitous Language shared by developers and domain experts. Key building blocks:

```
Strategic DDD:
  Domain → Subdomains (Core / Supporting / Generic)
  Subdomains → Bounded Contexts
  Bounded Contexts → Context Map (relationships)

Tactical DDD (inside a bounded context):
  Aggregate → Aggregate Root → Entities + Value Objects
  Domain Events → Domain Services → Repositories
```

Core domain gets most investment. Generic subdomains (email, billing) can be bought. Supporting subdomains get simple implementations.

## Gotchas
- Ubiquitous language must be enforced in code, not just docs
- One concept can have different meanings across bounded contexts — that is intentional
- DDD is overkill for CRUD-heavy domains with no complex business rules

## Related
- `bounded-context-design.md`
- `aggregate-root-pattern.md`
- `domain-events.md`
