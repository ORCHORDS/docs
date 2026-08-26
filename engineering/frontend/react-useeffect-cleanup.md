# react-useeffect-cleanup

**Issue:** Missing cleanup in useEffect causes memory leaks and stale closures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Subscriptions, timers, or event listeners keep running after component unmounts, causing "Can't perform a React state update on an unmounted component" warnings.

## Pattern / Solution
```tsx
useEffect(() => {
  const controller = new AbortController();
  fetch('/api/data', { signal: controller.signal })
    .then(r => r.json()).then(setData)
    .catch(e => { if (e.name !== 'AbortError') setError(e); });
  return () => controller.abort();
}, []);

useEffect(() => {
  const id = setInterval(tick, 1000);
  return () => clearInterval(id);
}, [tick]);
```

## Gotchas
- Cleanup runs before the next effect execution too, not only on unmount
- Closures in cleanup capture values from the render that registered the effect
- In React 18 Strict Mode effects run twice in dev; cleanup must be idempotent

## Related
- `react-hooks-rules.md`
- `browser-fetch-patterns.md`
