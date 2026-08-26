# javascript-main-thread

**Issue:** JavaScript execution monopolizes the main thread, blocking user interactions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The browser's main thread handles JavaScript execution, layout, paint, and user input. Long-running JS tasks (> 50ms) prevent the browser from responding to interactions.

## Pattern / Solution
1. Profile with Chrome DevTools Performance panel to find long tasks.\n2. Break up long synchronous loops with scheduler.yield().\n3. Move CPU-intensive work (data transformation, compression, parsing) to Web Workers.\n4. Reduce JavaScript bundle size and parse/compile time.\n5. Use time-slicing: process in chunks, yielding between each.

## Gotchas
- GC pauses count as main-thread blocking time; reduce allocation rates.\n- JSON.parse of large payloads can cause long tasks; parse in a Worker.\n- requestAnimationFrame callbacks run on the main thread; keep them fast.

## Related
long-task-detection, scheduler-yield-api, web-worker-offloading, total-blocking-time
