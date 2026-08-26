# Domain-Driven Design — Bounded Contexts, Context Mapping, and Event Storming

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your monolith uses a single `Customer` model shared across billing,
shipping, and marketing modules. The billing team adds a `taxId`
field that the marketing team does not need. The shipping team
defines `address` as a single string while billing requires
structured fields. Every change to the shared model requires
coordination across three teams and risks breaking unrelated
features. A junior developer asks "what does Customer mean?" and
gets three different answers depending on who they ask.

## Context

Bounded Context is the central strategic-design pattern in Domain-
Driven Design (DDD): the explicit boundary within which a domain
model and its ubiquitous language stay internally consistent. Martin
Fowler's canonical framing: "total unification of the domain model
for a large system will not be feasible or cost-effective." The same
term (e.g., "Customer," "Order") can legitimately mean different
things in different contexts, as long as each context is internally
coherent and boundaries are explicit. Context mapping patterns
describe the relationships between bounded contexts. Event Storming
(Alberto Brandolini) is the standard discovery workshop for
identifying bounded context boundaries before writing code.

## Bounded contexts

```
A bounded context defines:

  1. A linguistic boundary — terms have precise meaning WITHIN
     the context ("Customer" in Billing ≠ "Customer" in Marketing)

  2. A model boundary — entities, value objects, and aggregates
     are internally consistent

  3. An ownership boundary — one team owns one context

  4. A data boundary — each context owns its own data store

Identifying boundaries:
  → Follow shifts in language/terminology
  → Follow organizational/team ownership
  → NOT technical convenience (database tables, APIs)

  Strong signal a boundary is needed:
    Same noun requires different attributes or behavior
    in different parts of the organization
```

## Context mapping patterns

```
Pattern                 Relationship           When to use
──────────────────────────────────────────────────────────────
Shared Kernel           Two teams share a       Small, stable shared
                        small subset of         model; tight
                        model/code              coordination required

Customer-Supplier       Downstream needs        Upstream team can
                        prioritized by          prioritize downstream
                        upstream team           requirements

Conformist              Downstream adopts       No negotiating power;
                        upstream model as-is    upstream model is
                                                acceptable

Anti-Corruption         Downstream builds       Integrating with
Layer (ACL)             translation/adapter     legacy or third-party
                        layer                   systems

Open Host Service       Upstream exposes        Many consumers need
(OHS)                   well-defined protocol   access; decoupled
                        for many consumers      from internal model

Published Language      Shared interchange      Used alongside OHS
                        format (schema/DTO)     for formal contracts

Partnership             Mutual dependency,      Two teams with
                        coordinated releases    symmetric needs

Separate Ways           No integration          Cheaper than a bad
                                                integration
```

## Event Storming

```
Discovery workshop (Alberto Brandolini):

  Materials: orange sticky notes, wide wall or Miro board

  Process:
    1. Domain experts + engineers place orange stickies
       for DOMAIN EVENTS on a timeline
       ("Order Placed", "Payment Received", "Item Shipped")

    2. Add commands that trigger events
       ("Place Order", "Process Payment")

    3. Add actors who issue commands
       ("Customer", "Warehouse Staff")

    4. Add policies / reactions
       ("When Payment Received → Ship Item")

    5. Identify clusters of related events
       → Clusters reveal candidate AGGREGATES

    6. Identify vocabulary shifts between clusters
       → Vocabulary shifts reveal candidate BOUNDED CONTEXTS

  Event Storming is the most common practical technique for
  defining bounded contexts before code is written.
```

## Aggregates and aggregate roots

```
Aggregate:
  → Cluster of entities and value objects
  → Treated as one consistency/transactional boundary
  → External code references only the AGGREGATE ROOT
  → Root enforces invariants

Aggregate Root:
  → Single entry point for the aggregate
  → Only entity external code can reference
  → Dispatches domain events when state changes

Rules:
  → One transaction = one aggregate
  → Cross-aggregate consistency is eventual, not immediate
  → Keep aggregates small (prefer fewer entities)
  → Reference other aggregates by ID, not by object
```

```typescript
// TypeScript aggregate root example
class Order {
  private constructor(
    private readonly id: OrderId,
    private items: OrderItem[],
    private status: OrderStatus,
    private readonly events: DomainEvent[] = [],
  ) {}

  static create(id: OrderId, items: OrderItem[]): Order {
    if (items.length === 0) {
      throw new Error('Order must have at least one item');
    }
    const order = new Order(id, items, OrderStatus.Created);
    order.events.push(new OrderCreated(id, items));
    return order;
  }

  confirm(): void {
    if (this.status !== OrderStatus.Created) {
      throw new Error('Can only confirm created orders');
    }
    this.status = OrderStatus.Confirmed;
    this.events.push(new OrderConfirmed(this.id));
  }

  pullEvents(): DomainEvent[] {
    return this.events.splice(0);
  }
}
```

## Anti-Corruption Layer implementation

```typescript
// ACL translates between external (legacy) and internal models

// External legacy API response
interface LegacyCustomerDTO {
  cust_id: string;
  full_name: string;
  addr_line1: string;
  addr_line2: string;
  cust_type: number; // 1=individual, 2=business
}

// Internal domain model
class Customer {
  constructor(
    readonly id: CustomerId,
    readonly name: CustomerName,
    readonly address: Address,
    readonly type: CustomerType,
  ) {}
}

// Anti-Corruption Layer adapter
class LegacyCustomerAdapter {
  toDomain(dto: LegacyCustomerDTO): Customer {
    return new Customer(
      new CustomerId(dto.cust_id),
      new CustomerName(dto.full_name),
      Address.fromLines(dto.addr_line1, dto.addr_line2),
      dto.cust_type === 1
        ? CustomerType.Individual
        : CustomerType.Business,
    );
  }
}
```

## Relationship to microservices

```
Bounded context → natural (not automatic) service boundary:

  → Each context CAN map to one microservice
  → Each microservice owns its own data/model
  → ACL or OHS/Published Language governs inter-service calls
  → A single microservice commonly contains multiple aggregates

  Do NOT:
    → Split microservices before validating context boundaries
    → Assume 1:1 mapping between contexts and services
    → Create a microservice per aggregate (too granular)

  Validate boundaries first (Event Storming), then decide
  deployment topology (monolith, modular monolith, microservices).
```

## Anti-patterns

- **One giant shared domain model** — a single unified model
  across all teams leads to coordination overhead, naming
  conflicts, and unintended coupling. Draw explicit boundaries.
- **Treating boundaries as database schema splits** — bounded
  contexts follow language and ownership, not table structure.
  Two contexts can share a database if the models are isolated.
- **Skipping the ACL for legacy integration** — letting legacy
  model shapes leak into your domain model creates permanent
  coupling. Always translate at the boundary.
- **Aggregates that are too large** — crossing transactional
  boundaries that should be eventually consistent. Keep
  aggregates small and use domain events for cross-aggregate
  coordination.
- **Premature microservice extraction** — splitting into
  microservices before validating bounded context boundaries
  through Event Storming or similar discovery.

## Gotchas

- **Same term, different meaning is expected** — "Customer" in
  Billing and "Customer" in Marketing are DIFFERENT models by
  design. Do not force them into one shared type.
- **Shared Kernel requires discipline** — the shared subset must
  be small, explicitly agreed, and jointly tested. Shared Kernels
  that grow unchecked become the monolithic model they replaced.
- **Event Storming needs domain experts** — a workshop with only
  engineers produces a technical decomposition, not a domain
  decomposition. Domain experts provide the language shifts that
  reveal boundaries.
- **Context maps are living documents** — relationships between
  contexts change as teams and products evolve. Review and update
  context maps at least quarterly.

## Verification

- Bounded contexts identified through Event Storming or equivalent.
- Each context has a single owning team and ubiquitous language.
- Context map documents relationships between all contexts.
- Anti-Corruption Layers in place for legacy/third-party integration.
- Aggregates enforce invariants through the root entity.
- Cross-aggregate consistency uses domain events (eventual).
- Context boundaries validated before microservice extraction.

## Related

- `documentation/categories/architecture/event-sourcing-cqrs-projections.md`
- `documentation/categories/architecture/strangler-fig-migration-pattern.md`
- `documentation/categories/architecture/saga-pattern-distributed-transactions.md`

## Source URLs (verified 2026-08-16)

- Martin Fowler — BoundedContext — https://martinfowler.com/bliki/BoundedContext.html
- Context Mapping Patterns (O'Reilly / Vaughn Vernon) — https://www.oreilly.com/library/view/what-is-domain-driven/9781492057802/ch04.html
- Context Mapper — Open-Source DSL for Context Mapping — https://contextmapper.org/
- Domain-Driven Design with TypeScript — https://khalilstemmler.com/articles/categories/domain-driven-design/
