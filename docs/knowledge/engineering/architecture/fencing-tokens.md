# fencing-tokens

**Issue:** A distributed lock (Redis, Redlock, ZooKeeper, etcd lease) only guarantees that a *process believes* it holds the lock at the moment it checks. Between acquiring the lock and performing the protected write, anything can happen: a GC pause or VM freeze stops the process, the lease expires, another client acquires the lock, and then the paused process wakes up and writes anyway — clobbering the new lock holder's write. Martin Kleppmann's 2016 critique of Redlock made this gap famous: locks without storage-side validation are "neither fish nor fowl" — too heavyweight for mere efficiency, unsafe for correctness. Fencing tokens (monotonically increasing numbers issued with each lock acquisition and validated by the storage system) close this gap, but only if the storage layer actually supports token checks, which many popular stores do not natively. Architects need to understand when locks alone suffice, when fencing is mandatory, and how to build the token issuance/validation pipeline correctly.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why Locks Alone Are Unsafe

1. **The pause-and-resume failure.** Client A acquires lock, then stops (GC pause, VM migration, CPU starvation). Lease expires; client B acquires the lock and writes. A resumes mid-operation and writes with stale authority. The lock service behaved exactly as specified — the failure is between the lock check and the write, where no protocol message flows.
2. **Efficiency vs correctness locks.** If a lock merely prevents duplicate work (two workers building the same cache entry), a rare double-execution is harmless — a plain Redis lock with TTL, unique holder tokens (so only the owner can release), and automatic renewal is fine, and 2025-era guidance (OneUptime's Redis lock guide, Redis's own lock glossary) still recommends exactly that. If the lock guards money movement or uniqueness of a resource, no lease-based lock is sufficient without fencing.
3. **Redlock's specific weakness.** Redlock assumes bounded network delays, bounded process pauses, and bounded clock drift across independent Redis nodes — an asynchronous-system assumption the real world does not honor. A clock jump on one node can expire a lock early while a client still believes it holds it. This is why practitioners recommend consensus stores (ZooKeeper, etcd) over Redlock when correctness matters, and even then only as the *token issuer*, not the safety mechanism itself.

## How Fencing Tokens Work

1. **Issue on acquisition.** The lock service increments a strictly monotonic counter per lock name and returns the new value with the grant: client A gets 33, later client B gets 34. ZooKeeper's zxid/version, etcd's revision, or a dedicated counter (Redis INCR on a separate key with the caveats below) can serve as the source.
2. **Validate at the storage layer.** Every write to the protected resource must carry the token, and the storage system rejects writes whose token is lower than the highest token it has already accepted for that resource. When paused client A (token 33) wakes and writes, storage has already seen token 34 from B and refuses A's stale write. Safety now depends on one linearizable component — the storage system — instead of timing assumptions.
3. **The storage-support precondition.** Fencing only works if the store checks tokens: GCS/FIFO-capable systems, Chubby-style designs, and databases with conditional writes (compare token in a WHERE clause, or use versioned conditional updates) support it. Plain Redis values do not — Redis has no compare-and-set on an arbitrary counter applied to other keys, which is the classic gap noted across Stack Overflow and engineering write-ups. If your store cannot validate, fencing degrades to bookkeeping, not protection.
4. **Tokens must be per-resource and strictly increasing.** A single global counter is simplest and safe; per-lock counters reduce contention. Never reuse counters across unrelated lock names and never allow the counter to reset (persist it outside the lock service's ephemeral state, or derive it from a consensus log like etcd's revision, which is durable and monotonic).

## Design and Deployment Rules

1. **Choose the token source by consistency.** etcd revisions and ZooKeeper versions come from consensus and survive failover; a Redis INCR counter is faster but is lost or can regress on failover unless AOF-every-write with proper fsync is configured — and even then Redis replication is asynchronous, so a failover can expose an older counter. For correctness-critical resources, use the consensus-grade source.
2. **Make token checks atomic with the write.** In SQL, hold the token in a row column and write with "WHERE resource_id = ? AND fencing_token < ?" semantics (or optimistic concurrency on the token column). In object stores, use conditional puts with a version/generation number. Non-atomic check-then-write reintroduces the race you were trying to eliminate.
3. **Handle rejected writes deliberately.** A stale holder that gets fenced out must not retry blindly — it has lost leadership. Propagate a clear "fenced" error, abort the operation, and release/cleanup; retries belong at the orchestration layer with fresh lock acquisition.
4. **Pair with idempotency.** Fencing prevents stale writes, not duplicate *first* writes: a client may crash after storage accepts the write but before it learns of success. Keep operation ids and idempotency keys on the protected writes so the retry path is safe (see idempotency-design).
5. **Monitor token gaps and rejection rates.** Rising fencing rejections indicate lease TTLs are too short for the work being done (workers pausing past their leases) — lengthen leases or shrink the critical section rather than tolerating churn.

## When to Use What

1. **Efficiency-only locking.** Cache fill, deduplicated scheduled jobs, single-flight request coalescing: Redis SET NX PX with a random holder value and safe release via Lua compare-and-delete is the standard, cheapest answer.
2. **Correctness with a fenced store.** Writes to a database or storage system that supports conditional writes: consensus-based lock plus fencing tokens validated in the write path — the pattern Kleppmann endorses and the only one that survives arbitrary pauses.
3. **Correctness with an unfenced store.** Move the guard into the store itself: unique constraints, transactional compare-and-swap, or a serialized journal (outbox). Do not pretend a lease over an unfenced store is safe.
4. **Related articles.** distributed-lock-design covers lock mechanics; leader-election-patterns covers lease-based leadership; this article covers the safety net underneath both.
