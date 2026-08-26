# distributed-lock-design

**Issue:** Multiple instances of a service perform the same exclusive operation concurrently, causing conflicts
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A scheduled job runs on three application instances simultaneously, sending triplicate emails to users.

## Pattern / Solution
Use a distributed lock with a TTL (Redis SETNX with expiry, or Redlock for higher safety). The lock holder processes the job. Other instances fail to acquire the lock and skip. The TTL releases the lock if the holder crashes.

## Gotchas
Clock drift across nodes undermines Redlock correctness in theory. Fencing tokens (monotonically increasing lock version) prevent stale lock holders from making writes after losing the lock. Use distributed locks sparingly as they are a coordination point that reduces throughput.

## Related
idempotency-design, exactly-once-delivery, workflow-orchestration-patterns
