# clean-architecture-layers

**Issue:** Organizing code layers so inner layers never depend on outer layers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Changing the web framework or ORM requires touching business logic.

## Pattern / Solution
Concentric rings where dependencies point only inward.

```
   ┌──────────────────────────────────┐
   │  Frameworks & Drivers (outermost)│  ← Express, Django, SQLAlchemy
   │  ┌──────────────────────────────┐│
   │  │  Interface Adapters          ││  ← Controllers, Presenters, Gateways
   │  │  ┌──────────────────────────┐││
   │  │  │  Application Business    │││  ← Use Cases, Application Services
   │  │  │  ┌──────────────────────┐│││
   │  │  │  │  Enterprise Business ││││  ← Entities, Domain Objects
   │  │  │  └──────────────────────┘│││
   │  │  └──────────────────────────┘││
   │  └──────────────────────────────┘│
   └──────────────────────────────────┘
```

The Dependency Rule: source code dependencies must point inward only. Inner layers define interfaces; outer layers implement them.

## Gotchas
- Strict layering adds boilerplate; pragmatically skip layers for simple CRUD
- Data crosses boundaries as simple DTOs/structs, not domain objects
- "Clean Architecture" ≠ specific folder names; the dependency rule is the invariant

## Related
- `hexagonal-architecture.md`
- `vertical-slice-architecture.md`
