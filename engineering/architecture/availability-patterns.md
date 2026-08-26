# availability-patterns

**Issue:** Designing for high availability beyond just adding more servers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams equate availability with redundancy but miss failure modes at the dependency level.

## Pattern / Solution
Availability = uptime / (uptime + downtime). Nines table:
- 99% = 87.6 h/year downtime
- 99.9% = 8.76 h/year
- 99.99% = 52.6 min/year
- 99.999% = 5.26 min/year

Patterns:
1. Active-active failover: multiple nodes serving traffic simultaneously
2. Active-passive failover: hot standby promoted on failure
3. Health checks + auto-replacement via orchestrator
4. Graceful degradation: return cached/stale data when DB is down

```
                    ┌─────────────────┐
Client → DNS → LB ─┤  App Server A   ├─→ DB Primary
                   │  App Server B   ├─→ DB Replica (reads)
                   └─────────────────┘
```

## Gotchas
- Failover adds latency; clients need retry logic with exponential backoff
- Active-active requires conflict resolution if writes go to multiple nodes
- Health checks that are too aggressive cause flapping

## Related
- `circuit-breaker-design.md`
- `active-active-vs-active-passive.md`
- `disaster-recovery-architecture.md`
