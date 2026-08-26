# closure-memory-leaks

**Issue:** Closures inadvertently hold large objects alive
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A closure captures the outer scope. If a callback or event listener holds a closure referencing a large DOM tree or dataset, that data cannot be GC'd as long as the callback exists.

## Pattern / Solution
1. Minimize what closures capture; extract the needed values into local variables.\n2. Nullify references explicitly when work is done: largeData = null.\n3. Use WeakRef for caches that should not prevent GC.\n4. Avoid storing closures in global collections indefinitely.\n5. Diagnose with heap snapshot comparison in Chrome DevTools.

## Gotchas
- In React, components that subscribe to global stores but don't unsubscribe on unmount leak memory.\n- Promise chains that capture large objects keep them alive until the Promise settles.\n- Node.js EventEmitter: always call emitter.off() or use once() to prevent listener accumulation.

## Related
memory-management-js, garbage-collection-optimization, chrome-devtools-memory
