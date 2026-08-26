# consistent-hashing

**Issue:** When a cluster of caches, shards, or backend servers is fronted by a naive modulo hash (key hash mod N), changing N — adding a node, removing a failed one — remaps almost every key to a new owner, instantly invalidating entire caches and mass-migrating data. Consistent hashing solves this by mapping keys and nodes onto the same hash space so a membership change only relocates roughly 1/N of keys. The architecture question is not whether to use consistent hashing but which variant to use: ring hashing with virtual nodes, rendezvous (HRW), jump hash, or Maglev each trade lookup cost, memory, balance quality, and disruption characteristics differently, and picking the wrong one shows up as hot shards, stale cache divergence, or multi-gigabyte lookup tables.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core Algorithms and Tradeoffs

1. **Ring hash with virtual nodes.** The classic Ketama-style design: hash nodes onto a ring many times each (100-200 virtual nodes per physical node), and a key belongs to the next vnode clockwise. Lookup is O(log vnodes) with a sorted structure, and membership changes move only about 1/N of keys — but balance with few nodes is poor without many vnodes, which costs memory and cache-unfriendly lookups. The default general-purpose choice, used by Memcached clients and many sharded stores.
2. **Rendezvous hashing (HRW).** For each key, compute hash(key, node) for every node and pick the highest — the "highest random weight" method. Distribution quality is excellent, code is a few lines, membership changes relocate the theoretical minimum, and there is no vnode tuning; the cost is an O(n) lookup per key, which makes it ideal for small-to-medium clusters (a 2026 practitioner comparison puts rendezvous ahead for simplicity in pools up to low hundreds of nodes, with memory usage near zero since no ring structure is stored).
3. **Jump hash.** Computes bucket for a key in O(log n) with a very even distribution and no memory at all, but only supports adding/removing nodes at the end of a bucket sequence — a hard fit for elastic clusters where any node can fail, and a fine fit for fixed, append-only bucket sets. From Google, via Damien Gryski's widely-referenced algorithmic-tradeoffs survey.
4. **Maglev hashing.** Builds a fixed-size lookup table (prime-sized, e.g. 65537 or larger) via a permutation-based insertion so lookups are O(1) and every node receives a guaranteed near-equal share — designed for Google's network load balancer where per-packet lookup cost matters. The tradeoffs: table rebuilds on membership change are nontrivial, disruption is minimal but not strictly minimal, and memory is the table itself. Right choice for very high packets-per-second path selection.
5. **Bounded-load consistent hashing.** An orthogonal refinement (from a 2016 Google paper, still the standard answer to hot keys): cap any node's load at ceil(average * factor) by spilling overflowing keys to their next choice. Any base algorithm plus bounded loads stops viral keys from incinerating a single shard.

## Choosing by Workload

1. **Client-side cache sharding (Memcached/Redis clusters).** Ring hash with vnodes or rendezvous; disruption minimization is the priority because every remapped key is a cache miss storm on the backing store.
2. **Small, stable backend pools.** Rendezvous: simplest correct code, excellent balance, no tuning knobs; O(n) lookup is irrelevant when n is tens.
3. **Data-store partitioning with hot-key risk.** Ring or Maglev plus bounded loads; also prefer key designs that spread naturally (salt viral ids into multiple keys and scatter-gather).
4. **Packet/lookup-hot-path (per-request, millions per second).** Maglev or jump hash — memory is cheap, per-key CPU and branch predictability are what you are buying.
5. **Frequent autoscaling churn.** Ring with vnodes or Maglev tolerate arbitrary node add/remove; jump hash does not, and silently degrades into full remapping if nodes vanish mid-sequence.

## Implementation Pitfalls

1. **Hash function consistency across clients.** Every client must use the same hash function and same node-identity string (host:port, not IP that changes with redeploys), or clients route the same key to different nodes and your cache hit ratio quietly collapses. Pin the hash function (murmur3, xxhash) and node-naming scheme in a shared library.
2. **Vnode count tuning.** Too few virtual nodes gives lumpy balance (one physical node seeing 2x its share); too many wastes memory and slows ring construction on every membership change. 100-200 per node is the common band; measure your actual key-distribution skew rather than trusting defaults.
3. **Replica placement on the ring.** For replicated caches, taking the next k distinct physical nodes clockwise is correct, but naive implementations return the same vnode's owner k times or k vnodes on one physical box — enforce distinct-node checks.
4. **Ignoring state migration cost.** Consistent hashing minimizes remapping, not to zero: after a membership change, about 1/N of keys still move. For stateful stores you need a migration/ownership-handoff protocol, not just a new ring; for caches you just accept the misses.
5. **Weighted nodes.** Heterogeneous hardware needs per-node weights (more vnodes for bigger boxes in ring hash, weight-scaled scoring in HRW); an unweighted ring on mixed hardware underloads big nodes and overloads small ones.
6. **Membership flapping.** A flapping node causes repeated 1/N remaps; pair consistent hashing with health checks and a brief removal delay (or bounded-load spillover) so transient failures do not thrash the ring.

## Related Patterns

1. **Sharding strategies.** Consistent hashing is one sharding key-space strategy among range and directory-based sharding — see sharding-strategy for when ranges beat hashes.
2. **Distributed caching and cache-aside.** The primary deployment context; stampede protection (cache-stampede-prevention) composes with whatever placement scheme routes the keys.
3. **Service discovery.** Ring membership usually derives from a service registry; discovery latency and ring-update propagation determine how long clients route to dead nodes.
