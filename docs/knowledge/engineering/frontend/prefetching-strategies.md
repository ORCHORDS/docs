# prefetching-strategies

**Issue:** Dynamic imports load on demand causing a delay when the user triggers them
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Clicking "Open Editor" shows a 600ms spinner while the editor chunk downloads.

## Pattern / Solution
```ts
// Prefetch on hover
button.addEventListener('mouseenter', () => {
  import('./Editor'); // starts download, result ignored
});

// React Query prefetch on hover
const qc = useQueryClient();
<Link
  onMouseEnter={() => qc.prefetchQuery({ queryKey: ['post', id], queryFn: () => fetchPost(id) })}
  to={`/posts/${id}`}
>

// Next.js Link prefetches automatically in viewport (default)
<Link  prefetch={true}>Dashboard</Link>

// Vite: prefetch hint
<link rel="prefetch"  as="script">
```

## Gotchas
- prefetch priority is lower than preload; browser may defer it on slow connections
- Prefetching too many routes wastes bandwidth; limit to routes the user is likely to visit
- React Router and TanStack Router have built-in prefetch on link hover

## Related
- `code-splitting-dynamic-import.md`
- `html-performance-resource-hints.md`
