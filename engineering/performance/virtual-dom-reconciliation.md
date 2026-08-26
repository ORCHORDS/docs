# virtual-dom-reconciliation

**Issue:** Framework reconciliation causes unnecessary re-renders
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Virtual DOM frameworks diff a virtual representation against the previous state and apply minimal DOM updates. Poor component structure causes cascading re-renders despite no real data change.

## Pattern / Solution
1. Keep component trees shallow where possible; avoid prop drilling that triggers re-renders.\n2. Memoize expensive derived values with useMemo.\n3. Use stable references for functions passed as props (useCallback).\n4. Use React.memo for components that render with the same props.\n5. Profile with React DevTools Profiler to find unnecessary renders.

## Gotchas
- React.memo does a shallow comparison; objects/arrays created inline always fail equality checks.\n- Vue 3's Proxy-based reactivity is more granular than Vue 2's Object.defineProperty.\n- Svelte compiles away the virtual DOM entirely; consider compiler-based frameworks for performance.

## Related
react-render-optimization, react-memo-patterns, react-profiler, dom-manipulation-performance
