# garbage-collection-optimization

**Issue:** GC pauses cause jank during animations and interactions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
V8's garbage collector runs in the background but occasionally pauses JS execution. High allocation rates cause frequent GC pauses.

## Pattern / Solution
1. Reduce object allocation in hot paths: reuse objects, use object pools.\n2. Avoid creating closures in tight loops.\n3. Use TypedArrays for numeric data instead of regular arrays.\n4. Pre-allocate buffers for known-size data.\n5. In Chrome DevTools Performance, look for Minor GC / Major GC events in the timeline.

## Gotchas
- Modern V8 GC is incremental and concurrent -- most pauses are < 1ms. Major GC pauses can be 10-100ms.\n- Object shape changes (adding properties dynamically) deoptimize JIT code and increase GC pressure.\n- JSON.parse returns unoptimized objects; parse in Workers or use typed formats.

## Related
memory-management-js, closure-memory-leaks, javascript-main-thread
