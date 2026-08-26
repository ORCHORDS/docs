# Strangler Fig Pattern — Incremental Monolith-to-Microservices Migration

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your monolithic application has grown to the point where deployments take
hours, a single bug can bring down the entire system, and different
teams step on each other when merging code. Management wants to move to
microservices, but a full rewrite is estimated at 18-24 months with no
business value delivered until completion. Previous rewrite attempts
failed because the monolith continued evolving while the new system was
being built, creating a moving target. You need a migration strategy
that delivers incremental value while keeping the existing system
running.

## Context

The Strangler Fig pattern, named after the strangler fig tree that grows
around a host tree until it replaces it entirely, allows incremental
migration from a monolith to microservices. New functionality is built
as microservices alongside the existing monolith, and existing
functionality is gradually extracted. A facade (API gateway, reverse
proxy) routes traffic between old and new systems. The monolith shrinks
over time until it can be decommissioned. In 2026, this is the most
widely recommended migration pattern, endorsed by Martin Fowler, AWS,
Azure, and Google Cloud architecture guides. It is the opposite of a
big-bang rewrite.

## How it works

```
Phase 1: Identify — map the monolith's bounded contexts
Phase 2: Facade — add a routing layer in front of the monolith
Phase 3: Extract — build new microservices for identified contexts
Phase 4: Redirect — route traffic from monolith to new services
Phase 5: Shrink — remove extracted code from the monolith
Phase 6: Decommission — shut down the monolith when empty

┌──────────────────────────────────────────┐
│ Phase 1: All traffic → Monolith          │
│ [Client] → [Monolith (A+B+C+D)]         │
├──────────────────────────────────────────┤
│ Phase 2: Facade in front                 │
│ [Client] → [Facade] → [Monolith]        │
├──────────────────────────────────────────┤
│ Phase 3-4: Extract and redirect          │
│ [Client] → [Facade] → [Service A]       │
│                      → [Monolith (B+C+D)]│
├──────────────────────────────────────────┤
│ Phase 5-6: Continue until complete       │
│ [Client] → [Facade] → [Service A]       │
│                      → [Service B]       │
│                      → [Service C]       │
│                      → [Service D]       │
└──────────────────────────────────────────┘
```

## Selecting extraction candidates

```
Score each module on these criteria:

High extraction value:
  □ Independently deployable (clear API boundary)
  □ Different scaling requirements from the rest
  □ Different release cadence needed
  □ Owned by a distinct team
  □ Well-defined domain boundary (DDD bounded context)

Low extraction risk:
  □ Few database tables involved
  □ Minimal shared state with other modules
  □ Limited cross-module transactions
  □ Good test coverage
  □ Clear input/output contract

Start with: high value + low risk
Avoid starting with: core domain or shared data layer
```

## Facade implementation

### Reverse proxy (nginx)

```nginx
upstream monolith {
    server monolith.internal:8080;
}

upstream orders_service {
    server orders.internal:8080;
}

upstream users_service {
    server users.internal:8080;
}

server {
    listen 443 ssl;

    # Extracted: route to new microservice
    location /api/orders {
        proxy_pass http://orders_service;
    }

    # Extracted: route to new microservice
    location /api/users {
        proxy_pass http://users_service;
    }

    # Everything else: route to monolith
    location / {
        proxy_pass http://monolith;
    }
}
```

### Istio traffic routing (gradual)

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: api-routing
spec:
  hosts:
    - api.example.com
  http:
    # Canary: 10% to new service, 90% to monolith
    - match:
        - uri:
            prefix: /api/orders
      route:
        - destination:
            host: orders-service
          weight: 10
        - destination:
            host: monolith
          weight: 90

    # Fully migrated
    - match:
        - uri:
            prefix: /api/users
      route:
        - destination:
            host: users-service
          weight: 100

    # Default: monolith
    - route:
        - destination:
            host: monolith
```

## Data migration strategies

```
1. Shared database (short-term)
   → Both monolith and microservice read/write the same database
   → Fastest to implement, highest coupling
   → Use as a transitional step only

2. Database view (read migration)
   → Microservice owns a new database
   → Monolith reads from a view that joins both databases
   → Reduces coupling while maintaining read compatibility

3. Change data capture (CDC)
   → Monolith writes to its database
   → CDC (Debezium) streams changes to microservice's database
   → Eventual consistency between systems
   → No code changes in monolith required

4. Dual writes (avoid if possible)
   → Application writes to both databases
   → Risk of inconsistency if one write fails
   → Use CDC or events instead

5. Event-driven (target state)
   → Both systems publish/consume domain events
   → Each service owns its data store
   → Full decoupling achieved
```

## Anti-corruption layer

```
The anti-corruption layer (ACL) translates between the
monolith's data model and the microservice's domain model.

Monolith model          ACL              Microservice model
┌──────────────┐    ┌──────────┐    ┌──────────────────┐
│ user_tbl     │    │ Adapter  │    │ Customer entity  │
│  .usr_nm     │───►│ translat │───►│  .fullName       │
│  .usr_email  │    │ -es data │    │  .emailAddress   │
│  .active_flg │    │ models   │    │  .status (enum)  │
└──────────────┘    └──────────┘    └──────────────────┘

The ACL prevents legacy data models from contaminating
the new service's clean domain model.
```

## Feature flags for traffic control

```javascript
// Feature flag controls which system handles a request
async function handleOrderRequest(req, res) {
  const useNewService = await featureFlag.isEnabled(
    'orders-microservice',
    {
      userId: req.user.id,
      percentage: 25, // Gradual rollout
    }
  );

  if (useNewService) {
    return proxyToMicroservice(req, res, 'orders-service');
  }
  return proxyToMonolith(req, res);
}
```

## Anti-patterns

- **Big-bang cutover** — switching all traffic from monolith to
  microservice in one deployment. If the new service has bugs, there
  is no rollback path. Use gradual traffic shifting (1% → 10% → 50%
  → 100%) with monitoring at each stage.
- **Extracting the data layer first** — splitting the database before
  extracting application logic creates distributed transactions
  without the application architecture to support them. Extract
  application logic first, then migrate data.
- **Never shrinking the monolith** — building new services but
  leaving the old code in the monolith "just in case." Dead code in
  the monolith creates confusion and maintenance burden. Remove
  extracted code once the microservice is stable.
- **Extracting too many services at once** — migrating multiple
  modules simultaneously increases risk and cognitive load. Extract
  one bounded context at a time, stabilize it, then move to the next.

## Gotchas

- **Cross-cutting transactions** — if the monolith has transactions
  spanning the extracted module and other modules, splitting them
  requires implementing sagas or eventual consistency. Identify
  these transactions before extraction.
- **Shared authentication** — the monolith likely has a session-based
  auth mechanism that microservices cannot use directly. Implement
  a shared auth solution (OAuth2/JWT) before or during the first
  extraction.
- **Reporting queries** — analytical queries often join across
  multiple modules. After extraction, these joins become cross-service
  queries. Implement a read model or data warehouse for reporting
  before removing the monolith's reporting tables.
- **Migration fatigue** — strangler fig migrations take months to
  years. Teams lose motivation when the monolith still runs after
  12 months of work. Set milestones, celebrate extractions, and
  measure progress (percentage of traffic through microservices).

## Verification

- A facade (API gateway, reverse proxy) routes all external traffic.
- Extraction candidates are scored by value and risk.
- Traffic shifting is gradual with monitoring at each stage.
- Anti-corruption layers translate between legacy and new models.
- Data migration uses CDC or events, not dual writes.
- Extracted code is removed from the monolith after stabilization.
- Migration progress is tracked (percentage of traffic migrated).

## Related

- `documentation/categories/architecture/webassembly-component-model-patterns.md`
- `documentation/categories/deploy/progressive-canary-deployment-rollback.md`
- `documentation/categories/patterns/api-design-patterns.md`

## Source URLs (verified 2026-08-16)

- Strangler Fig Migration Pattern — https://oneuptime.com/blog/post/2026-01-24-strangler-fig-migration-pattern/view
- Strangler Fig Pattern: Migrate Legacy Systems Incrementally 2026 — https://appscale.blog/en/blog/microservices-pattern-strangler-fig-migration-2026
- Strangler Fig Pattern — AWS Prescriptive Guidance — https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/strangler-fig.html
- Strangler Fig Pattern — Azure Architecture Center — https://learn.microsoft.com/en-us/azure/architecture/patterns/strangler-fig
