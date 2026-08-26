# swr-vs-react-query

**Issue:** Choosing between SWR and TanStack Query for server state management
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Both libraries cache server data but differ in bundle size, feature set, and framework integration.

## Pattern / Solution
```
SWR (Vercel):
  + Tiny bundle (~4 KB)
  + Simple API; fast to learn
  + First-class Next.js integration
  - Limited mutation patterns
  - No query cancellation
  - Fewer devtools

TanStack Query:
  + Rich mutation support with optimistic updates
  + Infinite queries, paginated queries built-in
  + Excellent devtools
  + Framework agnostic (React, Vue, Solid, Svelte)
  - Larger bundle (~13 KB)
  - More configuration

SWR:
const { data, error } = useSWR('/api/user', fetcher);

TanStack Query:
const { data, error } = useQuery({ queryKey: ['user'], queryFn: fetchUser });
```

## Gotchas
- Both deduplicate requests globally; no manual caching needed
- TanStack Query's queryKey is typed and structural; SWR's key is a string or function
- For Next.js App Router with RSC, neither is necessary for initial data; use for client-side mutations

## Related
- `react-query-patterns.md`
- `apollo-client-patterns.md`
