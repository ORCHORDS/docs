# next-js-app-router-patterns

**Issue:** Pages Router mental model breaks in App Router; layouts and data fetching behave differently
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
getServerSideProps patterns no longer exist; layouts share state in unexpected ways.

## Pattern / Solution
```
app/
  layout.tsx        <- shared shell, rendered once
  page.tsx          <- route segment
  loading.tsx       <- Suspense boundary
  error.tsx         <- Error boundary
  not-found.tsx     <- 404 for this segment
  (group)/          <- route group, no URL segment
    dashboard/
      page.tsx
```

```tsx
// Nested layouts
export default function DashboardLayout({ children }) {
  return <div className="dashboard">{children}</div>;
}

// Data fetching directly in Server Components
export default async function Page() {
  const data = await fetchData();
  return <DataView data={data} />;
}
```

## Gotchas
- Layouts do not re-render on navigation within the same segment
- Use searchParams prop in page.tsx not useSearchParams in server components
- Template.tsx re-mounts on every navigation; layout.tsx does not

## Related
- `react-server-components.md`
- `next-js-data-fetching.md`
