# react-render-optimization

**Issue:** React components re-render too frequently
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Every state or context change triggers re-renders down the tree. In large applications, a single setState at the top can cascade thousands of renders per second.

## Pattern / Solution
1. Split context: separate frequently-changing state into its own context.\n2. Use useMemo for expensive computations.\n3. Use useCallback for stable function references.\n4. Use React.memo on leaf components that receive stable props.\n5. Use state colocation: keep state as close to where it's used as possible.

## Gotchas
- useMemo and useCallback add memory and comparison overhead; only use when profiling confirms benefit.\n- Context value object created inline re-renders all consumers on every parent render.\n- Zustand and Jotai have better subscription models than Context for high-frequency state.

## Related
react-memo-patterns, react-profiler, react-startTransition, virtual-dom-reconciliation
