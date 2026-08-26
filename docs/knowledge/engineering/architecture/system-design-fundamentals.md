# system-design-fundamentals

**Issue:** Core vocabulary and mental models for reasoning about large-scale systems
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Engineers asked to design systems without a shared framework make incompatible assumptions about scale, reliability, and cost.

## Pattern / Solution
Start every design session with three constraints: scale (requests/data volume), reliability (SLA/RPO/RTO), and cost envelope. Map these to the four pillars: scalability, availability, performance, maintainability.

```
User → Load Balancer → App Servers → Cache → DB
                              ↓
                         Message Queue → Workers
```

Sequence: clarify requirements → estimate scale → choose storage → define APIs → identify bottlenecks → iterate.

## Gotchas
- Premature optimization kills clarity; solve the stated scale, not 10x it
- "Stateless" services still need session state somewhere; be explicit about where
- Latency and throughput are inversely related at saturation

## Related
- `cap-theorem-explained.md`
- `availability-patterns.md`
