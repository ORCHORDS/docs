# active-active-vs-active-passive

**Issue:** Choosing the wrong redundancy model leads to either unnecessary cost or unmet availability targets
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A business targets 99.99% availability but runs active-passive with a 10-minute failover, which does not meet the target.

## Pattern / Solution
Active-active: all regions handle live traffic simultaneously, providing zero-downtime failover and lower latency globally. Active-passive: only the primary region handles traffic; the secondary is warm and ready to take over. Active-active requires conflict-free data models or strong consistency replication.

## Gotchas
Active-active with a relational database requires careful conflict resolution or a globally consistent database at significant cost. Active-passive RTO depends entirely on DNS TTL and health check speed.

## Related
multi-region-architecture, data-replication-strategies, disaster-recovery-architecture
