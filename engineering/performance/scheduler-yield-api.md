# scheduler-yield-api

**Issue:** Long synchronous tasks cannot be broken up without complex setTimeout chains
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
scheduler.yield() returns a Promise that resolves when the browser is ready to continue, yielding control back to the event loop. Available in Chrome 115+; polyfillable with setTimeout.

## Pattern / Solution
1. Basic yield: await scheduler.yield() inside a loop.\n2. Yield only when task time exceeds a threshold: check performance.now() - start > 50.\n3. Polyfill: const yieldToMain = () => new Promise(r => setTimeout(r, 0)).\n4. Use scheduler.postTask with priority for more control.

## Gotchas
- Yielding too frequently increases total execution time; yield at natural batch boundaries.\n- scheduler.yield() is not the same as setTimeout(fn, 0) -- it has higher priority.\n- Not supported in Firefox/Safari yet; the setTimeout polyfill works cross-browser.

## Related
javascript-main-thread, long-task-detection, inp-optimization, requestidlecallback-patterns
