# hexagonal-architecture

**Issue:** Decoupling application core from infrastructure so it can be tested and adapted independently
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests require a real database; swapping a third-party library requires changing business logic.

## Pattern / Solution
Also called Ports & Adapters. The core defines ports (interfaces); adapters implement them.

```
         [HTTP Adapter]   [CLI Adapter]   [Test Adapter]
               ↓                ↓               ↓
         ┌─────────────────────────────────────┐
         │         Application Core            │
         │  (Domain + Application Services)    │
         │                                     │
         │  Port: OrderRepository (interface)  │
         │  Port: EmailSender (interface)      │
         └──────────────────┬──────────────────┘
                            ↓
         [SQL Adapter]  [Kafka Adapter]  [SMTP Adapter]
```

Driving ports (left): initiated by external actors (HTTP, CLI, tests).
Driven ports (right): initiated by the core, implemented by infrastructure.

## Gotchas
- DTOs cross the boundary; do not pass domain objects into adapters
- Port interfaces belong to the core, not to the adapter
- Over-engineering for simple CRUD apps; apply where domain complexity justifies it

## Related
- `clean-architecture-layers.md`
- `application-services.md`
- `repository-pattern-ddd.md`
