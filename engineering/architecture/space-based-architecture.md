# Space-Based Architecture

> **When to use:** Extreme, unpredictable, bursty concurrency against a
> dataset that the relational database cannot serve—flash sales, ticket
  drops, viral events, live leaderboards. The database is always the
> bottleneck, and the only way to win is to not touch it during the spike.

Also called **space-based** because the processing units (the "spaces") live
in memory across many nodes, coordinated by a data grid, with no single
bottleneck. Originated in high-frequency trading and adopted by e-commerce
for Black Friday-scale events.

## Symptom

You need space-based architecture when:

- The database CPU pegs at 100% during traffic spikes, even though app
  servers are idle. Reads and writes both hit the DB and it cannot keep up.
- You have tried every caching pattern (`cache-aside-pattern.md`,
  `read-through-cache.md`, `write-behind-cache.md`) and the DB is still the
  bottleneck because writes still go through it synchronously.
- Adding more app servers does not help—in fact it makes it worse, because
  each new server adds connection-pool pressure on the shared DB.
- Traffic is spiky and unpredictable: 10x normal in 30 seconds, then back to
  baseline. You cannot provision the DB for peak economically.
- You are sharding (`sharding-strategy.md`) but cross-shard coordination and
  consistency are eating the gains.

The core diagnosis: **the relational database is a shared, synchronous
bottleneck that cannot be horizontally scaled, and your load pattern makes
vertical scaling uneconomic.**

## Core Idea

Eliminate the synchronous database from the request path entirely. Every app
node holds a partition of the working set **in memory**, backed by a
distributed in-memory data grid (IMDG: Hazelcast, Apache Ignite, Coherence,
Redis Cluster). Updates write to the grid, not the DB. A background process
asynchronously drains the grid to the database for durability.

```
[Request] -> [Processing Unit + in-memory data] <-> [Data Grid (replicated/partitioned)]
                                                              |
                                                  [async drain, batched]
                                                              v
                                                     [Relational DB]  (durable, eventual)
```

Five components:

1. **Processing units** — app instances, each holding data in memory.
2. **Data grid** — distributes and replicates data across units.
3. **Backing store** — the relational DB, written asynchronously.
4. **Write-behind** — coalesces and batches grid updates to the DB.
5. **Data pumps** — move data in/out of the grid for recovery.

## Gotchas

- **In-memory data is volatile.** A full grid failure before the write-behind
  drains loses committed updates. Replication across nodes mitigates but does
  not eliminate this. You must be able to tolerate a small, bounded data loss
  window—or accept the cost of synchronous replication (which slows you down).
- **Eventual consistency is mandatory, not optional.** The DB lags behind the
  grid by seconds to minutes. If a downstream system reads from the DB
  expecting the latest write, it will see stale data. This rules out
  space-based for payment capture, money movement, or anything requiring
  strong consistency (use a saga or a synchronous path for those).
- **This is the most complex architecture in this knowledge base.** Do not
  adopt it lightly. Operationally you now run an in-memory distributed
  system with partition tolerance, recovery, and rebalancing concerns on top
  of your normal stack. Many teams that try it end up with a fragile,
  expensive cache that behaves nothing like a DB.
- **Complex queries are painful.** You have given up SQL joins against the
  authoritative store. Aggregations must be precomputed (materialized in the
  grid) or done via map-reduce across the grid. Reporting typically reads
  from the DB, which is eventually consistent.
- **Capacity planning is about memory, not CPU.** Your grid must fit the
  working set in RAM across all nodes with headroom for replication. If the
  dataset grows beyond RAM, you evict and fall back to disk—which is slow.
  Monitor memory pressure relentlessly.
- **Rebalancing on node join/leave is expensive.** When you scale out or a
  node dies, the grid redistributes partitions. During rebalancing, latency
  spikes. Design for graceful degradation and test under simulated node loss.
- **Cold start is a problem.** On a full restart, the grid is empty and must
  be repopulated from the DB. Until that completes, performance is terrible.
  Keep a warm standby or accept a degraded start window.
- **Testing is very hard.** Concurrency bugs, race conditions, and ordering
  issues only appear at scale across multiple nodes. You cannot reproduce
  them on a single developer laptop. Invest in chaos testing and a staging
  grid that mirrors production topology.
- **Vendor lock-in is real.** IMDGs are proprietary, expensive, and hard to
  swap out. Open-source options (Ignite, Hazelcast) reduce but do not
  eliminate this risk.

## Practical Example (Conceptual — Flash Sale Inventory)

The classic use case: a concert ticket drop where 100k users hit "buy" in
the same second. A relational DB cannot serve this. A space-based grid can.

```typescript
// Each processing unit holds a partition of inventory in memory.
// The grid ensures updates are atomic and replicated.
class InventorySpace {
  // Reserves N seats for an event, atomically, in-memory.
  async reserve(eventId: string, quantity: number): Promise<boolean> {
    // Entry processor runs ON the node owning this eventId's partition.
    // No network round-trip to a DB. Locking is local to the partition.
    return await grid.executeOnKey(eventId, (inventory) => {
      if (inventory.available >= quantity) {
        inventory.available -= quantity;
        inventory.held += quantity;
        return true; // committed to the grid immediately
      }
      return false;
    });
  }
}

// Write-behind: drain held inventory to the DB every 5 seconds, batched.
setInterval(async () => {
  const batches = await grid.scanLocal("inventory", (i) => i.held > 0);
  for (const b of batches) {
    await db.batchUpdate(b);              // durable, eventual
    await grid.apply(b.id, (i) => { i.held = 0; });
  }
}, 5000);
```

The user gets a synchronous, correct answer ("you got 2 tickets") in
microseconds. The DB learns about it a few seconds later. During the spike,
the DB is untouched.

## When NOT to use space-based

- **Anything requiring strong consistency** (payments, ledger, auth). The
  write-behind lag is unacceptable.
- **Steady, predictable load.** If your DB handles normal traffic fine and
  spikes are mild, caching + read replicas are far simpler.
- **Small datasets that fit comfortably in a single DB.** No reason to add a
  data grid.
- **Teams without deep distributed-systems experience.** This is an
  expert-level architecture that punishes naivety.

## Decision Checklist

1. Is the DB the bottleneck under bursty load, unfixable by caching? -> Maybe
2. Can you tolerate seconds-to-minutes of eventual consistency? -> Maybe
3. Does the working set fit in aggregate RAM across nodes? -> Maybe
4. Is the load pattern genuinely spiky and extreme (10x+)? -> Worth it
5. Do you have the team to operate an IMDG in production? -> Only then proceed

Prefer simpler options first: `cache-aside-pattern.md`,
`write-behind-cache.md`, `sharding-strategy.md`,
`rate-limiter-design.md` + `load-shedding-patterns.md`. Reach for space-based
only when you have exhausted those and the DB is still the wall.

## Related Articles

- `cache-aside-pattern.md`, `read-through-cache.md` — simpler caching, try first
- `write-behind-cache.md` — the write-behind component, in isolation
- `distributed-caching.md` — the data grid foundation
- `sharding-strategy.md` — partitioning the data grid
- `consistency-patterns.md` — the consistency trade-offs you are signing up for
- `backpressure-patterns.md`, `load-shedding-patterns.md` — burst-handling alternatives
