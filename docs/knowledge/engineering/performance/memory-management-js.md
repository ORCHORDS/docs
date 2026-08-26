# memory-management-js

**Issue:** JavaScript heap grows unbounded, causing slowdowns
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
JS garbage collection is automatic but not instant. Holding references to objects prevents GC. In long-running SPAs, memory leaks accumulate across navigations and interactions.

## Pattern / Solution
1. Remove event listeners when components unmount: use removeEventListener or AbortController.\n2. Clear intervals and timeouts: store handles and clearInterval/clearTimeout on cleanup.\n3. Use WeakMap/WeakSet for DOM-to-data mappings to allow GC.\n4. Avoid accidental globals by using const/let instead of var.\n5. Profile with Chrome DevTools Memory > Allocation Timeline.

## Gotchas
- React class component lifecycle componentWillUnmount must clean up timers and listeners.\n- React hooks: effects should return a cleanup function.\n- Closures capturing large arrays/objects can hold them alive longer than intended.

## Related
garbage-collection-optimization, closure-memory-leaks, chrome-devtools-memory
