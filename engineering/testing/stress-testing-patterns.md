# stress-testing-patterns

**Issue:** Finding system limits and failure behavior under extreme load
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Performance testing finds p95 under normal load. Stress testing finds what happens beyond that — graceful degradation or catastrophic failure.

## Pattern / Solution
Stress test stages (k6):
```js
export const options = {
  stages: [
    { duration: "2m", target: 100 },
    { duration: "5m", target: 100 },
    { duration: "2m", target: 200 },
    { duration: "5m", target: 200 },
    { duration: "2m", target: 300 },  // beyond expected capacity
    { duration: "5m", target: 300 },
    { duration: "10m", target: 0 },   // recovery check
  ],
};
```

What to measure:
- At what VU count does p99 exceed SLA?
- Does the system recover after overload (no stuck connections)?
- Are errors graceful (503) or catastrophic (connection reset)?
- Does memory/CPU return to baseline after load drops?

## Gotchas
- Never stress test production without warning — use staging
- Set up alerts before stress testing — know when to stop
- Memory leaks show up in soak tests, not stress tests

## Related
- `performance-testing-k6.md`
- `chaos-testing-approaches.md`
- `load-test-scenarios.md`
