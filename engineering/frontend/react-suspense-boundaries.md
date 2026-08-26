# react-suspense-boundaries

**Issue:** Async data fetching without Suspense shows inconsistent loading UI
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Different page sections show spinners at different times, causing layout shift and jarring UX.

## Pattern / Solution
```tsx
import { Suspense } from 'react';

function Page() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <ErrorBoundary fallback={<ErrorMessage />}>
        <UserProfile />
      </ErrorBoundary>
    </Suspense>
  );
}

// Next.js App Router: loading.tsx is an implicit Suspense boundary
// app/dashboard/loading.tsx wraps the segment automatically
```

## Gotchas
- Suspense does not catch errors; pair with an ErrorBoundary
- Multiple Suspense siblings fetch in parallel, avoiding waterfalls
- React 18 concurrent rendering required for full Suspense support

## Related
- `react-error-boundaries.md`
- `react-server-components.md`
