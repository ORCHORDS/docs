# load-test-scenarios

**Issue:** Designing representative load test scenarios for different traffic patterns
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Load tests that do not reflect real traffic patterns give misleading results — testing 100% reads when production is 80% writes.

## Pattern / Solution
Common scenario types:
- **Baseline**: steady low load (10% of peak) — establish normal p95
- **Ramp up**: gradually increase load — find breaking point
- **Spike**: sudden 10x increase — test auto-scaling
- **Soak**: 70% load for 24h — catch memory leaks and resource exhaustion
- **Breakpoint**: increase until failure — find max throughput

Traffic mix example (k6):
```js
export const options = {
  scenarios: {
    reads: { executor: "constant-vus", vus: 80, duration: "5m", exec: "readUser" },
    writes: { executor: "constant-vus", vus: 20, duration: "5m", exec: "createUser" },
  },
};

export function readUser() { /* GET /users/:id */ }
export function createUser() { /* POST /users */ }
```

## Gotchas
- Warm up caches before measuring — cold cache skews results
- Use production-like data volume — empty DB tests are not representative
- Include think time (sleep) to simulate real users

## Related
- `performance-testing-k6.md`
- `stress-testing-patterns.md`
