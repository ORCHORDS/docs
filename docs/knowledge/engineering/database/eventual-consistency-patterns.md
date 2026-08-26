# eventual-consistency-patterns

**Issue:** Distributed systems cannot guarantee immediate consistency without sacrificing availability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Read replicas serving stale data. Cache not yet invalidated after write. Users seeing old data after update.

## Pattern / Solution
Design for eventual consistency explicitly: use optimistic UI updates, version vectors or timestamps to detect staleness, read-your-writes guarantees by routing user reads to primary or using session tokens.

## Gotchas
- Read-your-writes is broken when user switches devices or load balancer routes to different replica
- Conflict resolution for concurrent writes needs explicit policy (last-write-wins, merge, reject)
- Idempotency keys prevent duplicate processing in retry scenarios

## Related
- read-replicas-routing
- cqrs-read-write-split
- distributed-transactions-saga
