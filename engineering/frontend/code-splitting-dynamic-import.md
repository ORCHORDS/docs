# code-splitting-dynamic-import

**Issue:** Loading all JavaScript upfront delays time-to-interactive
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A rich text editor and a chart library load on every page even though most users never open those features.

## Pattern / Solution
```tsx
import React, { lazy, Suspense } from 'react';

// Lazy load heavy components
const RichEditor = lazy(() => import('./RichEditor'));
const Chart = lazy(() => import('./Chart'));

function Page() {
  return (
    <Suspense fallback={<Spinner />}>
      {showEditor && <RichEditor />}
    </Suspense>
  );
}

// Dynamic import in event handler (no Suspense needed)
button.addEventListener('click', async () => {
  const { initMap } = await import('./map');
  initMap(container);
});

// Vite magic comments for chunk naming
const Module = lazy(() => import(/* webpackChunkName: "editor" */ './Editor'));
```

## Gotchas
- React.lazy only works with default exports; named exports require a re-export wrapper
- Prefetch on hover to avoid loading delay on click
- Group related components in the same chunk: () => Promise.all([import('./A'), import('./B')])

## Related
- `webpack-code-splitting.md`
- `prefetching-strategies.md`
