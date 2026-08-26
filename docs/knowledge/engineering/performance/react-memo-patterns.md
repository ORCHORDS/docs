# react-memo-patterns

**Issue:** React.memo not preventing re-renders due to unstable references
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
React.memo wraps a component to skip re-render if props haven't changed (shallow equality). It fails when parent passes new object/function references on every render.

## Pattern / Solution
1. Stabilize function props with useCallback.\n2. Stabilize object props with useMemo.\n3. Pass primitive values when possible instead of objects.\n4. Use a custom comparator for deep equality: React.memo(Component, (prev, next) => isEqual(prev, next)).\n5. Extract static data outside the component to avoid recreating it on render.

## Gotchas
- Deep equality comparators are expensive; use only for complex objects where shallow fails frequently.\n- React.memo only prevents the function call; if children use context, they can still re-render.\n- Overusing memo adds complexity; profile first to confirm the optimization is needed.

## Related
react-render-optimization, react-profiler, virtual-dom-reconciliation
