# cap-theorem-explained

**Issue:** Understanding the fundamental trade-off between consistency, availability, and partition tolerance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams pick databases without understanding what guarantees they lose under network failures.

## Pattern / Solution
CAP states a distributed system can guarantee at most two of three properties simultaneously.

```
         Consistency
            /\
           /  \
          /    \
   CP ---+------+ CA
(HBase) /        \ (RDBMS single-node)
       /    AP    \
      +------------+
   (Cassandra, DynamoDB)
     Availability -- Partition Tolerance
```

In practice, network partitions happen, so the real choice is CP vs AP: sacrifice availability to stay consistent (CP) or serve stale data to stay available (AP).

PACELC extends CAP: even without partitions, choose latency vs consistency.

## Gotchas
- "CA" systems only exist without partitions, i.e., single-node
- Eventual consistency is not the same as no consistency
- CP systems can still be highly available under normal operation

## Related
- `consistency-patterns.md`
- `availability-patterns.md`
- `acid-vs-base-tradeoffs.md`
