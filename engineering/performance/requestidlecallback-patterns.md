# requestidlecallback-patterns

**Issue:** Background work competes with critical rendering tasks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
requestIdleCallback (rIC) schedules work during browser idle periods, after all high-priority tasks are complete. Ideal for non-critical initialization, analytics flushing, and prefetching.

## Pattern / Solution
1. Use requestIdleCallback with a deadline argument to check timeRemaining() before each unit of work.\n2. Use timeout option to ensure work runs eventually even if the browser is never idle.\n3. Check deadline.timeRemaining() before each unit of work.\n4. Polyfill with setTimeout(fn, 0) for unsupported browsers.

## Gotchas
- rIC is not available in Safari; always provide a setTimeout fallback.\n- Idle callbacks can be delayed indefinitely on busy pages without a timeout.\n- Do not perform layout reads inside rIC without wrapping in rAF first.

## Related
scheduler-yield-api, javascript-main-thread, analytics-performance-impact
