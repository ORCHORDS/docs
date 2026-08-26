# react-query-patterns

**Issue:** Manual fetch/useEffect for server state leads to race conditions and stale data
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Multiple components fetch the same endpoint independently; loading and error states are duplicated everywhere.

## Pattern / Solution
```ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const { data, isPending, error } = useQuery({
  queryKey: ['posts', filters],
  queryFn: () => fetchPosts(filters),
  staleTime: 60_000,
});

const qc = useQueryClient();
const mutation = useMutation({
  mutationFn: createPost,
  onSuccess: () => qc.invalidateQueries({ queryKey: ['posts'] }),
});

// Prefetch on hover
qc.prefetchQuery({ queryKey: ['post', id], queryFn: () => fetchPost(id) });
```

## Gotchas
- queryKey must fully describe the fetch params and be serializable
- staleTime: Infinity for static data; 0 always refetches on mount
- Use useSuspenseQuery for Suspense integration

## Related
- `react-suspense-boundaries.md`
- `swr-vs-react-query.md`
