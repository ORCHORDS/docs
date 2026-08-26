# TanStack Query — Server State Management

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Multiple components issue identical `fetch` calls inside
`useEffect`. Race conditions produce stale data when components
unmount and remount. Loading/error states are duplicated
everywhere. Background updates on mobile are inconsistent because
window focus events are not wired to the fetch lifecycle.

## Context

TanStack Query (formerly React Query) separates server state —
data that lives on the server and is fetched asynchronously —
from client UI state. It provides a shared cache keyed by a
query key, automatic background refetching, and a consistent
loading/error/data lifecycle.

| Concept        | Description                                      |
|----------------|--------------------------------------------------|
| Query key      | Serializable array that identifies a cache entry |
| staleTime      | How long cached data is considered fresh         |
| gcTime         | How long unused data stays in cache (default 5m) |
| Optimistic upd.| Mutate the cache before the server confirms      |

## useQuery vs useMutation

`useQuery` reads server state. It runs automatically, caches the
result, and re-runs when the key changes or the entry goes stale.
`useMutation` writes. It does not cache results and is invoked
imperatively.

```ts
import {
  useQuery, useMutation, useQueryClient,
} from '@tanstack/react-query';

const { data, isPending, isError } = useQuery({
  queryKey: ['posts', { page, tag }],
  queryFn: () => fetchPosts({ page, tag }),
  staleTime: 60_000,
});

const qc = useQueryClient();
const { mutate } = useMutation({
  mutationFn: (draft: NewPost) => createPost(draft),
  onSuccess: () =>
    qc.invalidateQueries({ queryKey: ['posts'] }),
});
```

## Query Key Design

Query keys are the cache address and must fully describe the
fetch parameters. Define them in one place:

```ts
export const postKeys = {
  all:    () => ['posts']          as const,
  list:   (f: PostFilters) =>
    [...postKeys.all(), f]         as const,
  detail: (id: string) =>
    ['post', id]                   as const,
};
```

Invalidating `['posts']` cascades to every key that starts with
`'posts'` — unfiltered list and all filtered variants.

## Optimistic Updates

```ts
const { mutate: likePost } = useMutation({
  mutationFn: (id: string) => toggleLike(id),
  onMutate: async (id) => {
    await qc.cancelQueries({ queryKey: postKeys.detail(id) });
    const previous = qc.getQueryData(postKeys.detail(id));
    qc.setQueryData(postKeys.detail(id), (old: Post) => ({
      ...old, likes: old.likes + 1, likedByMe: true,
    }));
    return { previous };
  },
  onError: (_err, id, ctx) =>
    qc.setQueryData(postKeys.detail(id), ctx?.previous),
  onSettled: (_, __, id) =>
    qc.invalidateQueries({ queryKey: postKeys.detail(id) }),
});
```

Always `cancelQueries` before the optimistic write to prevent
an in-flight response from overwriting the optimistic state.

## Infinite Scroll with useInfiniteQuery

```ts
const { data, fetchNextPage, hasNextPage } =
  useInfiniteQuery({
    queryKey: ['feed', filters],
    queryFn: ({ pageParam = null }) =>
      fetchFeed({ cursor: pageParam, ...filters }),
    getNextPageParam: (last) => last.nextCursor ?? undefined,
    initialPageParam: null,
  });

const posts = data?.pages.flatMap((p) => p.items) ?? [];

// Trigger from an IntersectionObserver sentinel element
useEffect(() => {
  if (inView && hasNextPage) fetchNextPage();
}, [inView, hasNextPage]);
```

Set `maxPages` to bound memory growth on long-running sessions.

## Background Refetching and Next.js Export

On React Native override the focus listener to fire on
`AppState` changes: `focusManager.setEventListener((h) => { const
sub = AppState.addEventListener('change', s => h(s==='active'));
return () => sub.remove(); })`.

Web default (`refetchOnWindowFocus: true`) already handles tab
switches. Disable it for polling-heavy dashboards where a focus
event should not add an extra round trip.

**Next.js static export (`output: 'export'`):** prefetch on the
server and dehydrate into the page component:

```ts
// app/posts/page.tsx (server component)
import { dehydrate, HydrationBoundary, QueryClient }
  from '@tanstack/react-query';

export default async function PostsPage() {
  const qc = new QueryClient();
  await qc.prefetchQuery({
    queryKey: postKeys.list({ page: 1 }),
    queryFn: () => fetchPosts({ page: 1 }),
  });
  return (
    <HydrationBoundary state={dehydrate(qc)}>
      <PostList />
    </HydrationBoundary>
  );
}
```

The client hydrates from the dehydrated state; the first render
is synchronous with no loading spinner. Background refetches
begin automatically after hydration.

## Anti-patterns

- Using `useEffect` + `useState` for server data alongside
  TanStack Query — two caches fight each other.
- Setting `staleTime: 0` globally — every mount triggers a
  network request, even for data fetched seconds ago.
- Storing server data in Zustand/Redux when the query cache
  already holds it.
- Calling `invalidateQueries` with no key — invalidates every
  cache entry simultaneously.
- Missing `await cancelQueries` in `onMutate` — in-flight
  responses overwrite the optimistic state.

## Gotchas

- `gcTime` (formerly `cacheTime`) controls garbage collection of
  unused entries, not staleness — two separate concepts.
- Query keys are deep-equality compared; key objects with the
  same fields in different order are treated as identical.
- `useSuspenseQuery` requires a `<Suspense>` boundary — a missing
  boundary causes an unhandled throw during render.
- `useInfiniteQuery` pages accumulate in memory; set `maxPages`.

## Verification

- **Unit test:** mock `queryFn`; assert `isPending`, `data`,
  and `isError` transitions with React Testing Library.
- **Integration:** run against MSW; assert background refetch
  fires after `window.dispatchEvent(new Event('focus'))`.
- **Bundle:** `npm ls @tanstack/react-query` — no duplicates.

## Related

- `frontend/swr-vs-react-query.md`
- `frontend/react-suspense-boundaries.md`
- `frontend/optimistic-ui-updates-rollback.md`
- `frontend/next-js-caching-strategy.md`

## Source URLs (verified 2026-08-17)

- https://tanstack.com/query/latest/docs/framework/react/overview
- https://tanstack.com/query/latest/docs/framework/react/guides/query-keys
- https://tanstack.com/query/latest/docs/framework/react/guides/optimistic-updates
- https://tanstack.com/query/latest/docs/framework/react/guides/infinite-queries
- https://tanstack.com/query/latest/docs/framework/react/guides/advanced-ssr
