# react-usecallback-pitfalls

**Issue:** useCallback misuse produces stale closures and unnecessary complexity
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Callbacks wrapped in useCallback still cause child re-renders, or they capture stale state values.

## Pattern / Solution
```tsx
// Stale closure bug
const handleClick = useCallback(() => {
  console.log(count); // stale if count missing from deps
}, []); // BUG

// Fixed
const handleClick = useCallback(() => {
  console.log(count);
}, [count]);

// React 19 useEffectEvent avoids the tradeoff entirely
const handleClick = useEffectEvent(() => {
  console.log(count); // always fresh, stable reference
});
```

## Gotchas
- useCallback only helps when the child is wrapped in React.memo
- Every dep change creates a new function reference anyway
- Inline functions are fine for most non-memoized children

## Related
- `react-usememo-when-to-use.md`
- `react-render-props-pattern.md`
