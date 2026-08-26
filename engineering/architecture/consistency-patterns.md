# consistency-patterns

**Issue:** Designing systems with explicit consistency guarantees appropriate to the use case
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
"Eventual consistency" is treated as a single thing; teams get surprised by read-your-writes violations or stale reads.

## Pattern / Solution
Consistency spectrum from strong to weak:

```
Strong → Linearizable → Sequential → Causal → Read-your-writes → Monotonic → Eventual
```

Linearizable: reads always reflect the latest write. Use for leader election, distributed locks.
Causal: operations that causally relate are seen in order. Use for chat, collaborative editors.
Read-your-writes: a user always sees their own writes. Achieved by sticky sessions or reading from primary.
Eventual: all replicas converge given no new writes. Use for DNS, shopping carts.

## Gotchas
- Sticky sessions break with node failure; use consistent hashing or session tokens
- Causal consistency requires vector clocks or similar metadata
- Monotonic reads prevent seeing older versions after a newer one — requires routing to same replica

## Related
- `cap-theorem-explained.md`
- `data-replication-strategies.md`
