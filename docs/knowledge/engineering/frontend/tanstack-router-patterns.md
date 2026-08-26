# tanstack-router-patterns

**Issue:** Type-safe routing with search param validation is not available in React Router
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Search params are typed as string | null everywhere; navigating to a non-existent route is not caught at compile time.

## Pattern / Solution
```ts
import { createRootRoute, createRoute, createRouter } from '@tanstack/react-router';
import { z } from 'zod';

const rootRoute = createRootRoute({ component: RootLayout });

const postsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/posts',
  validateSearch: z.object({
    page: z.number().default(1),
    filter: z.string().optional(),
  }),
  component: PostsPage,
});

// Fully typed navigation
const navigate = useNavigate({ from: '/posts' });
navigate({ search: (prev) => ({ ...prev, page: prev.page + 1 }) });

// Typed search params
const { page, filter } = postsRoute.useSearch();
```

## Gotchas
- File-based routing with Vite plugin generates the route tree automatically
- Loaders run before the component renders; use them for data fetching
- Route types are inferred from the route tree; no manual type declarations needed

## Related
- `react-router-v7-patterns.md`
- `state-management-patterns.md`
