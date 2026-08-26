# Cell-Based Architecture

> **When to use:** When you have outgrown a single failure domain and need to
> isolate blast radius, scale independently, and keep teams autonomous—without
> the full operational cost of unconstrained microservices.

Also known as **cellular architecture**. Popularized by AWS (how they built
S3 and DynamoDB) and by eBay, Shopify, and GitHub for their largest services.

## Symptom

You need cell-based architecture when:

- A bad deployment, a hot key, or a noisy-neighbor tenant takes down *all*
  customers at once. The blast radius is "everyone."
- The database is the single bottleneck. You cannot scale horizontally
  because every request hits the same shared store.
- One team's rollout windows are blocked by another team's change freeze.
  Everyone ships on the same calendar because everyone shares the same stack.
- A regional outage cascades globally because there is one logical deployment
  with no isolation boundary.
- You have tried sharding (`sharding-strategy.md`) but the cross-shard query
  complexity is killing you, and routing is fragile.

The core pain is: **one failure kills everyone, and one deployment gates
everyone.** Cells fix both by introducing hard isolation.

## Core Idea

A **cell** is a self-contained, independent unit of deployment that contains
everything needed to serve a subset of traffic: its own app servers, its own
database, its own caches, its own queue. Cells are identical in code but
isolated in data and infrastructure.

```
                    [Cell Router]
                   /      |      \
            [Cell A]  [Cell B]  [Cell C]
            app+db    app+db    app+db
            (users    (users    (users
             0-1M)     1-2M)     2-3M)
```

- **Cell router** sits in front and directs each request to the correct cell
  based on a routing key (`tenantId`, `userId`, `region`).
- **No cross-cell calls** (or only via well-defined async paths). Each cell
  owns its data exclusively. This is the hard part and the whole point.
- **Failure is contained.** If Cell B's database dies, only Cell B's users
  are affected. Cells A and C are untouched.
- **Deployment is independent.** Roll out to Cell C first (canary), then B,
  then A. If something breaks, it breaks for one cell's worth of users.

This is **sharding taken all the way up the stack**: not just the database,
but the entire application tier.

## Gotchas

- **The routing key is load-bearing forever.** Choose it carefully. It must
  be stable, available on every request, and evenly distributable.
  `tenantId` is ideal for B2B; a hash of `userId` works for B2C. Get this
  wrong and you cannot rebalance without downtime.
- **Cross-cell queries are forbidden—until someone needs one.** "Show me all
  orders across all tenants" cannot be a simple SQL join anymore. You need
  either (a) a separate analytics cell fed by event replication, (b) a
  fan-out-and-gather query layer, or (c) an aggregate read model. Plan for
  this from day one; retrofitting it is painful.
- **Cell router is a new single point of failure and a new bottleneck.** It
  must be stateless, highly available, and fast. If it goes down, everything
  goes down. Anycast DNS + multiple router replicas is typical.
- **Uneven cell sizing wastes money.** If one cell holds 80% of traffic and
  another holds 2%, you are paying for idle capacity. Use consistent hashing
  or explicit capacity planning to keep cells balanced, and have a cell-split
  procedure ready.
- **Migrating a tenant between cells is hard.** You will need it eventually
  (rebalancing, isolating a noisy tenant, compliance). Build the migration
  tooling before you need it—doing it under fire is brutal.
- **Operational complexity multiplies.** Each cell is a full stack to monitor,
  patch, back up, and debug. Automation is non-negotiable: cells must be
  provisioned from code (Terraform/Pulumi), identically.
- **Testing must be per-cell.** A schema migration must roll out cell by cell.
  Feature flags (`feature-flag-architecture.md`) must be evaluated per-cell.
  Your deploy pipeline must be cell-aware.
- **Cost is higher than a single deployment.** You are paying for N copies of
  infrastructure. The payoff is resilience and isolation—if you do not need
  those, do not pay this cost.
- **Cold starts for new cells.** Spinning up Cell N+1 means warming caches,
  populating reference data, and validating routing. Automate cell bootstrap.

## Practical Example

**Cell router (simplified, stateless, sticky by tenant):**

```typescript
// Map tenantId -> cell deterministically. Same tenant always hits same cell.
const CELLS = [
  { id: "cell-a", url: "https://cell-a.internal", weight: 0.33 },
  { id: "cell-b", url: "https://cell-b.internal", weight: 0.33 },
  { id: "cell-c", url: "https://cell-c.internal", weight: 0.34 },
];

function routeCell(tenantId: string): Cell {
  // Consistent hashing so rebalancing moves minimal tenants
  const hash = sha256(tenantId).readUInt32BE(0);
  return CELLS[hash % CELLS.length];
}

// In the request handler
app.use((req, res, next) => {
  const tenantId = req.headers["x-tenant-id"];
  if (!tenantId) return res.status(400).send("tenant required");
  req.cell = routeCell(tenantId);
  next();
});
```

**Routing table for rebalancing (editable without redeploy):**

```json
{
  "cell-a": ["tenant_001", "tenant_002", "tenant_003"],
  "cell-b": ["tenant_004", "tenant_005"],
  "cell-c": ["tenant_006"]
}
```

**Canary deploy to one cell at a time:**

```bash
./deploy.sh cell-c    # 33% of tenants
# monitor error rate for 1 hour
./deploy.sh cell-b    # 66%
./deploy.sh cell-a    # 100%
```

## When NOT to use cells

- **Single-tenant or small-scale systems.** The isolation benefit is zero and
  the cost is real.
- **Systems that fundamentally need a single global view** (a global
  leaderboard, a single shared inventory). Cells force you to give up easy
  cross-cutting queries.
- **Teams that cannot automate infrastructure.** Manual cell provisioning will
  collapse under N-fold operational load.

## Decision Checklist

1. Does one failure take down all customers at once? -> Consider cells
2. Is the database the bottleneck that sharding alone cannot fix? -> Cells
3. Do you have multiple regions and need regional isolation? -> Cells
4. Can your system tolerate "no cross-cell joins"? -> Cells viable
5. Can your team automate infrastructure-as-code? -> Cells viable

## Related Articles

- `sharding-strategy.md` — cell-based is full-stack sharding
- `multi-region-architecture.md` — cells as a regional isolation pattern
- `bulkhead-pattern.md` — cells are the macro version of bulkheads
- `multi-tenancy-architecture.md` — tenant-to-cell routing
- `tenant-routing-patterns.md` — how to route requests to the right cell
- `canary-deployment-architecture.md` — cell-by-cell rollout
