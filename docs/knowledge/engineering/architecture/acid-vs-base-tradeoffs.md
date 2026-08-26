# acid-vs-base-tradeoffs

**Issue:** Choosing between strong transactional guarantees and high availability
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Developers default to ACID without understanding the cost, or choose BASE without understanding the consistency implications.

## Pattern / Solution
ACID: Atomicity, Consistency, Isolation, Durability — guaranteed by relational DBs using locks and WAL.
BASE: Basically Available, Soft state, Eventually consistent — used by distributed NoSQL systems.

```
ACID (PostgreSQL):
BEGIN;
  UPDATE accounts SET balance = balance - 100 WHERE id = 1;
  UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT; -- all or nothing

BASE (Cassandra):
Write to quorum nodes → propagate async → reads may return stale
```

Use ACID for financial ledgers, inventory, order state. Use BASE for user profiles, analytics counters, activity feeds.

## Gotchas
- Some NoSQL DBs offer optional ACID per-document (MongoDB, DynamoDB transactions) at cost
- "Eventually consistent" requires application logic to handle conflicts
- Two-phase commit achieves ACID across services but is a latency and availability killer

## Related
- `cap-theorem-explained.md`
- `consistency-patterns.md`
- `idempotency-design.md`
