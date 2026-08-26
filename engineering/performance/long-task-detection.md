# long-task-detection

**Issue:** Long tasks not instrumented, making them hard to diagnose in production
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The Long Tasks API (PerformanceObserver with longtasks type) reports any main-thread task > 50ms. Without instrumentation, long tasks are invisible in RUM data.

## Pattern / Solution
1. Observe long tasks with PerformanceObserver type longtasks.\n2. Report entry.duration, entry.attribution, and entry.startTime to your RUM tool.\n3. Correlate long tasks with user interactions to identify INP contributors.\n4. Set a budget: alert when task duration > 200ms.

## Gotchas
- Long Tasks API attribution is coarse; use User Timing marks for precision.\n- The API is not available in all browsers; feature-detect before using.\n- Long tasks during page load are counted in TBT; tasks during interaction affect INP.

## Related
javascript-main-thread, inp-optimization, total-blocking-time, scheduler-yield-api
