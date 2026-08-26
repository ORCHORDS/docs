# chrome-devtools-performance

**Issue:** Need to profile main-thread activity and identify bottlenecks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Chrome DevTools Performance panel records CPU activity, paints, layouts, and network requests in a timeline. Essential for diagnosing slow interactions, layout thrashing, and long tasks.

## Pattern / Solution
1. Open DevTools > Performance > Record; interact with the page; Stop.\n2. Enable CPU throttling (4x or 6x) to simulate slower devices.\n3. Look for red triangles on the Main thread -- these indicate long tasks.\n4. Expand tasks to see call stacks; identify hot functions.\n5. Use Bottom-Up and Call Tree views to find the costliest functions.

## Gotchas
- Recording overhead itself skews results slightly; keep recordings short and focused.\n- User Timing marks (performance.mark) appear in the timeline -- instrument your code.\n- Forced reflow warnings indicate layout thrashing; fix by batching reads before writes.

## Related
long-task-detection, layout-thrashing-prevention, javascript-main-thread, react-profiler
