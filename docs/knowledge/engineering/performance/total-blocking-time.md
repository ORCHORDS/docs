# total-blocking-time

**Issue:** Total Blocking Time is high, correlated with poor INP
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
TBT sums the blocking portions of long tasks (> 50ms) between FCP and TTI. It is the lab proxy for INP. A good score is < 200ms.

## Pattern / Solution
1. Break long tasks into smaller chunks with scheduler.yield().\n2. Move synchronous work out of the critical rendering path.\n3. Use Web Workers for CPU-intensive computations.\n4. Audit with Lighthouse > Avoid long main-thread tasks.\n5. Defer or remove unused JavaScript.

## Gotchas
- TBT only counts blocking time between FCP and TTI; tasks after TTI still affect INP.\n- Third-party scripts (analytics, chat widgets) are a common TBT culprit.\n- Webpack bundle splitting reduces parse time but multiple round trips can increase network time.

## Related
inp-optimization, long-task-detection, javascript-main-thread, web-worker-offloading
