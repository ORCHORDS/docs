# react-error-boundaries

**Issue:** Unhandled render errors crash the entire React tree
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A TypeError in a nested component blanks the entire page with no recovery path for the user.

## Pattern / Solution
```tsx
import { ErrorBoundary } from 'react-error-boundary';

<ErrorBoundary
  fallbackRender={({ error, resetErrorBoundary }) => (
    <div>
      <p>{error.message}</p>
      <button onClick={resetErrorBoundary}>Retry</button>
    </div>
  )}
  onError={(error, info) => logError(error, info.componentStack)}
>
  <FeatureComponent />
</ErrorBoundary>

// Reset on route change
<ErrorBoundary resetKeys={[pathname]} ...>
```

## Gotchas
- Error boundaries only catch render and lifecycle errors, not async errors
- Use try/catch inside event handlers and async functions
- Must be class components if writing from scratch without the library

## Related
- `react-suspense-boundaries.md`
- `react-server-components.md`
