# react-deferred-value

**Issue:** Expensive derived renders block urgent updates
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
useDeferredValue defers a value update, showing stale content while the new render happens in the background. Useful for search inputs with expensive result rendering.

## Pattern / Solution
1. const deferredQuery = useDeferredValue(query); use deferredQuery for expensive list render.\n2. Show a loading indicator when deferredQuery !== query.\n3. Combine with React.memo on the expensive component so it only re-renders when deferredQuery changes.\n4. Use for: autocomplete results, filtered lists, data visualization updates.

## Gotchas
- useDeferredValue does not batch network requests; it only defers rendering.\n- On fast devices, deferred value may match immediately -- the stale indicator flickers.\n- Not available in React < 18.

## Related
react-startTransition, react-render-optimization, inp-optimization
