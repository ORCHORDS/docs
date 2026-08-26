# load-testing-methodology

**Issue:** Performance issues only emerge in production under real load
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Load testing validates that a system performs acceptably under expected and peak load conditions. Without it, capacity limits, connection pool exhaustion, and memory leaks are discovered in production.

## Pattern / Solution
1. Define scenarios: ramp-up, steady state, spike, soak (long-duration).\n2. Use k6 for developer-friendly scripting: export default function() { http.get('https://example.com'); }\n3. Establish baselines before changes; compare after.\n4. Monitor server-side metrics during test: CPU, memory, DB connections, error rate.\n5. Test in an environment that mirrors production; shared environments produce noisy results.

## Gotchas
- Load generators themselves can be a bottleneck; use distributed load testing for high VU counts.\n- Synthetic traffic may not match real user behavior; supplement with production traffic shadowing.\n- Ramp up gradually; sudden spikes may mask real-world behavior that builds over time.

## Related
performance-budget-setup, performance-regression-detection, rum-vs-synthetic-metrics
