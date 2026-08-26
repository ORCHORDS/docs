# next-js-parallel-routes

**Issue:** Rendering multiple independent page sections with separate loading and error states
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A dashboard sidebar and main content area need independent Suspense boundaries and separate error handling.

## Pattern / Solution
```
app/dashboard/
  layout.tsx
  @sidebar/
    page.tsx
    loading.tsx
  @main/
    page.tsx
    error.tsx
  page.tsx
```

```tsx
// layout.tsx
export default function Layout({ children, sidebar, main }) {
  return (
    <div className="layout">
      {sidebar}
      {main}
      {children}
    </div>
  );
}
```

## Gotchas
- Slot names (@ prefix) must match the prop name in the layout
- Default exports in each slot are required for catch-all fallback
- Parallel routes enable modal sheets (intercepting routes + parallel slots)

## Related
- `next-js-intercepting-routes.md`
- `next-js-app-router-patterns.md`
