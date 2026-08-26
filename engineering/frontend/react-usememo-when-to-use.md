# react-usememo-when-to-use

**Issue:** Overuse of useMemo adds overhead; underuse causes expensive recalculations
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Profiler shows either excessive memoization overhead for cheap ops, or expensive derivations re-running on every render.

## Pattern / Solution
```tsx
// Worth memoizing: expensive derivation
const sorted = useMemo(() => largeArray.slice().sort(compareFn), [largeArray]);

// Not worth it: cheap computation
const doubled = value * 2; // no useMemo needed

// Stable reference for child prop
const config = useMemo(() => ({ theme, lang }), [theme, lang]);
```

## Gotchas
- useMemo does not guarantee the memo is kept; React may discard it
- Dependency arrays must be complete or stale value is used
- Measure first with React DevTools Profiler before adding memos

## Related
- `react-usecallback-pitfalls.md`
- `react-context-performance.md`
