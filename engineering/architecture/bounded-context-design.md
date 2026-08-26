# bounded-context-design

**Issue:** Defining explicit boundaries where a model is valid and internally consistent
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
"Customer" means different things in sales, shipping, and billing — a single shared model becomes a mess of nullable fields.

## Pattern / Solution
Each bounded context owns its own model of shared concepts.

```
Sales Context:       Customer { id, name, leadScore }
Shipping Context:    Customer { id, deliveryAddress, preferences }
Billing Context:     Customer { id, paymentMethods, invoices }
```

Context Map patterns:
- Shared Kernel: teams share a small model subset (high coordination cost)
- Customer-Supplier: upstream provides API, downstream consumes
- Conformist: downstream adopts upstream model entirely
- Anti-Corruption Layer: downstream translates upstream model
- Published Language: shared formal schema (e.g., OpenAPI, Protobuf)

## Gotchas
- Bounded contexts map to teams, not always to microservices
- Shared DB across bounded contexts re-introduces coupling
- Context boundaries should be driven by domain, not technical convenience

## Related
- `domain-driven-design-basics.md`
- `anti-corruption-layer.md`
- `aggregate-root-pattern.md`
