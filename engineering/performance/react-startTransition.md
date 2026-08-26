# react-startTransition

**Issue:** Urgent UI updates (typing, clicking) are delayed by non-urgent state updates
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
startTransition marks state updates as non-urgent. React prioritizes urgent updates (user input) and defers transition updates, preventing input lag.

## Pattern / Solution
1. Wrap non-urgent updates: startTransition(() => setState(newValue)).\n2. Use useTransition hook to get isPending indicator for loading UI.\n3. Apply to: search results, tab switches, list re-renders triggered by filter changes.\n4. Combine with useDeferredValue for derived values.

## Gotchas
- Transitions are not for async work (fetches); use Suspense for data loading.\n- Updates inside startTransition may be interrupted and retried; ensure they are idempotent.\n- Not a silver bullet; profiling must confirm the bottleneck before adding transitions.

## Related
react-deferred-value, inp-optimization, react-render-optimization
