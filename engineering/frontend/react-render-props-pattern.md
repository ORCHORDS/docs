# react-render-props-pattern

**Issue:** Logic reuse between components without custom hooks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A data-fetching component needs to render different UI in different places without duplicating fetch logic.

## Pattern / Solution
```tsx
function DataFetcher({ url, render }) {
  const { data, loading } = useFetch(url);
  return render({ data, loading });
}

<DataFetcher url="/api/users" render={({ data, loading }) =>
  loading ? <Spinner /> : <UserList users={data} />
} />

// children-as-function variant
<Mouse>{({ x, y }) => <Cursor x={x} y={y} />}</Mouse>
```
Custom hooks have largely replaced render props but render props remain useful when the consumer fully controls rendering structure.

## Gotchas
- Inline render functions recreate on every render; wrap in useCallback if child is memoized
- TypeScript generics needed for type-safe render props
- Deeply nested render props create callback hell; prefer hooks

## Related
- `react-compound-components.md`
- `react-controlled-vs-uncontrolled.md`
