# Cache Coherence Write Through Vs Write Behind

## Scope

This article addresses the engineering trade-offs between write-through and write-behind caching as applied to application-level caches in front of a system of record. It explains how each policy interacts with cache coherence, durability, latency, and the failure modes that follow from them. The discussion includes the role of cache invalidation, versioning, generation counters, and read-your-writes consistency. It is project-neutral and applies to caches of any kind: in-process caches, distributed caches, edge caches, and database read replicas. It does not address hardware cache coherence protocols; those are referenced only to make the conceptual distinction clear.

## Workflow or implementation guidance

A write-through cache updates the cache synchronously with the system of record. The handler writes to the system of record, waits for the durable acknowledgement, and only then writes to the cache. The cache is therefore guaranteed to reflect the latest committed state, and a read after a successful write returns the new value. The cost is the additional synchronous round trip from the application to the cache on every write, and the latency tail of the slower of the two writes. Write-through is the right default when correctness is more important than write throughput: financial transactions, inventory, and any state where a stale cache can cause a user-visible error.

A write-behind (also called write-back) cache accepts the write into the cache, returns immediately, and asynchronously propagates the write to the system of record. The cache acts as a temporary buffer, often coalescing multiple writes to the same key into one durable write. The cost is the durability gap: a crash between the cache write and the durable write loses data unless the cache itself is durable. Write-behind is appropriate for high-write workloads where the system of record cannot absorb the write rate, where losing the last few seconds of writes is acceptable (analytics counters, session keep-alive, leaderboard updates), and where the cache is implemented on durable storage such as Cloudflare Durable Objects or a database with strong durability.

The first decision is therefore about durability tolerance. If the application cannot tolerate any data loss between the user-visible acknowledgement and the durable write, write-through is mandatory. The second decision is about latency. If the synchronous write to the cache adds unacceptable tail latency to a write-heavy path, write-behind is justified. The third decision is about coherence. A write-through cache is naturally coherent in the simple case because the same code path that writes to the system of record also writes to the cache. A write-behind cache requires explicit handling for "did my write reach the system of record yet?" because the answer is asynchronous.

In distributed deployments, cache coherence also depends on how caches in different regions or processes see each other's writes. A single global cache (KV with eventual consistency, Redis with replication) introduces a window during which one node sees a stale value. Generation counters—also called cache versions or "cas" tokens—attached to each cached entry solve this by letting a reader detect that its cached value is older than the system of record's current version, and refetch. Write-through caches that include the generation counter in the same write call are coherent in practice; write-behind caches must apply the generation counter atomically with the durable write, otherwise readers can see the new value with an old generation or vice versa.

## Controls

Cache controls must ensure that (a) the cache cannot return a value that is logically newer than the durable system of record, (b) the cache cannot indefinitely serve a value that has been invalidated, and (c) the failure modes of the cache (eviction, expiry, network partition) do not corrupt the system of record. For write-through, the control is the synchronous two-step write wrapped in a transactional boundary: either both succeed or the caller retries. For write-behind, the control is a write-ahead log inside the cache and a background drain that is idempotent against the system of record.

Versioning controls apply to both. Each cached entry carries a version (a generation counter, a Lamport timestamp, or a hash of the entity's current state). Readers compare the cached version to a system-of-record check before serving a "stale" value, falling through to the system of record if the version is older. This is the application-level equivalent of a coherence protocol, and it is what prevents the classic "stale read after write" failure.

Logging and tracing must distinguish between cache hits, cache misses, cache reads against the system of record (cache stampede), and rejected writes (write-behind backpressure). Without these signals, the cache cannot be tuned.

## Validation evidence

Validation for a write-through cache is straightforward: every write path must demonstrably update both the system of record and the cache, and every read path must demonstrate that the value returned matches the value last written. A coherence test runs concurrent reads and writes from multiple clients and asserts that no read returns a value older than the most recent write for any single client (read-your-writes) and that the cache eventually matches the system of record after all writes complete.

Validation for a write-behind cache is harder. The test must cover: (a) durability under cache crash, (b) coalescing behaviour under bursty writes, (c) ordering of writes (a write-behind cache must not reorder writes such that a later write reaches the system of record before an earlier one), and (d) staleness visibility to readers. Crash tests should forcibly kill the cache process between the user-visible acknowledgement and the durable write, and assert that the data is either correctly persisted (if the write-ahead log survived) or honestly reported as lost (if it did not). Latency tests should prove that the write path does not block on the durable write.

## Failure modes and correction

The dominant failure mode for write-through is split brain: the cache is updated but the system of record write failed, or vice versa. The cache and the system of record are now inconsistent. The cure is to perform the system of record write first, observe the durable acknowledgement, then write to the cache; treat a cache write failure as a soft error and let the cache populate on the next read. A second write-through failure is treating the cache as the source of truth. The cache is an accelerator; the system of record must be the source of truth, and any code path that bypasses the system of record risks divergence.

The dominant failure mode for write-behind is data loss on cache crash. The cure is a write-ahead log on durable storage inside the cache tier, plus an idempotent background drain that can replay after a crash without producing duplicate downstream effects. A second write-behind failure is unbounded memory growth. A cache that buffers writes faster than the drain can deliver them will eventually exhaust memory. The cure is backpressure: the cache rejects writes when its buffer is full, and the caller falls back to a write-through path.

A coherence failure common to both is the read-after-write from a different process. A user writes on Node A, then reads on Node B, and Node B's cache still holds the old value. The cure is generation counters, fan-out invalidation, or short cache TTLs combined with a "fetch if not present" path that re-validates against the system of record.

## Limitations

Write-through always pays the cost of two synchronous writes per write request, which is unacceptable for write-heavy workloads against a slow system of record. Write-behind pays the cost of an asynchronous consistency model: any code path that assumes the value is durable immediately after acknowledgement is incorrect, and that includes billing, audit, and compliance flows. Neither policy protects against a cache that simply returns stale data due to a bug in the cache key or in the invalidation logic—the application layer must own correctness. Finally, application-level cache coherence is not free: generation counters, versioned keys, and stampede protection each add their own complexity, and the total complexity can exceed the simplicity of going straight to the system of record for some workloads.

## Canonical sources

- Eric Evans — *Domain-Driven Design: Tackling Complexity in the Heart of Software* ("Blue Book"), repository and aggregate chapters for system-of-record discipline
- Martin Fowler — *Patterns of Enterprise Application Architecture* (PoEAA), Repository and Unit of Work patterns and the discussion of cache vs. system of record
- CMU 15-451 / 18-421 lecture notes and course materials on cache coherence, as a conceptual reference for application-level coherence models: https://en.wikipedia.org/wiki/Cache_coherence
- AWS Architecture Blog and Well-Architected Reliability pillar, caching guidance: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/
