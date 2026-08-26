# chrome-devtools-memory

**Issue:** Page memory grows over time, causing slowdowns or crashes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Memory leaks in SPAs accumulate over navigation events. Chrome DevTools Memory panel provides heap snapshots, allocation timelines, and allocation sampling to find leaks.

## Pattern / Solution
1. Take heap snapshot before and after a user flow; compare in Comparison view.\n2. Use Allocation instrumentation on timeline to see which allocations persist.\n3. Sort by Retained Size to find large object trees.\n4. Look for detached DOM nodes -- elements removed from DOM but held in JS closures.\n5. Use WeakRef/WeakMap for caches that should not prevent GC.

## Gotchas
- Triggering GC before a snapshot (DevTools trash icon) gives cleaner baselines.\n- Framework internals often appear as top retainers; look for your code in retained paths.\n- Memory panel only shows JS heap; native memory (WebGL buffers) requires additional tooling.

## Related
memory-management-js, garbage-collection-optimization, closure-memory-leaks, nodejs-heap-snapshots
