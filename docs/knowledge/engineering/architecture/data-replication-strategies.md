# data-replication-strategies

**Issue:** Keeping data consistent across multiple regions or replicas is a fundamental distributed systems challenge
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A read replica serves stale data because replication lag exceeds the consistency expectation of the application.

## Pattern / Solution
Synchronous replication: writes block until all replicas confirm (strong consistency, higher latency). Asynchronous replication: writes confirm after the primary (lower latency, potential lag). Use read-your-writes consistency by routing reads to the primary for a session window after a write.

## Gotchas
Asynchronous replication can lose committed writes during failover. Monitor replication lag actively. Applications must tolerate or route around replication lag explicitly.

## Related
multi-region-architecture, active-active-vs-active-passive, cap-theorem-explained
