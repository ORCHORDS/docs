# Infinite Scroll with IntersectionObserver — Mobile Safari Quirks & Cloudflare D1 Keyset Pagination

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Infinite scroll fires multiple simultaneous requests on mobile Safari, or never fires
at all because the sentinel element is invisible in the iOS virtual keyboard overlay.
On the backend, `OFFSET`-based pagination slows to >500 ms at page 50+ on Cloudflare
D1. Skeleton loaders flash for <100 ms and then disappear before content is ready,
causing a jarring content jump.

## Context

example project (example.com) feeds rely on infinite scroll to surface music tracks and playlists.
The list is paginated via a Cloudflare Worker that queries D1. Mobile Safari has known
quirks with IntersectionObserver: callbacks fire when the root is the document viewport
and the virtual keyboard changes the visual viewport size but not the layout viewport.

---

## IntersectionObserver Mobile Safari Quirks

| Issue | Affected | Root Cause | Fix |
|---|---|---|---|
| Callback fires on keyboard open | iOS Safari ≤16 | Visual viewport resize triggers re-evaluation | Debounce callbacks, guard with `isIntersecting` |
| Threshold ignored at 0 | iOS Safari ≤15 | Float precision rounding | Use `threshold: 0.01` not `0` |
| Root margin ignored when root is null | iOS Safari <15.4 | Bug — layout viewport not respected | Polyfill or use a visible explicit root |
| Multiple simultaneous callbacks | All mobile | Fast scroll past sentinel | Lock with `isFetching` ref |

---

## React Hook — useInfiniteScroll

```tsx
// hooks/useInfiniteScroll.ts
import { useEffect, useRef, useCallback } from 'react';

interface Options {
  onLoadMore: () => void;
  hasNextPage: boolean;
  isFetching: boolean;
  /** rootMargin in CSS syntax — default '200px' triggers before sentinel is visible */
  rootMargin?: string;
}

export function useInfiniteScroll({
  onLoadMore,
  hasNextPage,
  isFetching,
  rootMargin = '200px',
}: Options) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  // Stable ref so the IntersectionObserver callback never becomes stale
  const stateRef = useRef({ hasNextPage, isFetching, onLoadMore });

  useEffect(() => {
    stateRef.current = { hasNextPage, isFetching, onLoadMore };
  });

  const observe = useCallback(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const { hasNextPage, isFetching, onLoadMore } = stateRef.current;
        // Guard: only fire when truly intersecting and not already loading
        if (entries[0]?.isIntersecting && hasNextPage && !isFetching) {
          onLoadMore();
        }
      },
      {
        // iOS Safari ≤15 ignores rootMargin when root is null;
        // use 0.01 threshold to avoid float-precision rounding bug
        threshold: 0.01,
        rootMargin,
      },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [rootMargin]);

  useEffect(observe, [observe]);

  return sentinelRef;
}
```

### Usage

```tsx
// components/TrackFeed.tsx
export function TrackFeed() {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({ ... });

  const sentinelRef = useInfiniteScroll({
    onLoadMore: fetchNextPage,
    hasNextPage: !!hasNextPage,
    isFetching: isFetchingNextPage,
  });

  return (
    <ul>
      {data?.pages.flatMap((p) => p.tracks).map((t) => (
        <TrackRow key={t.id} track={t} />
      ))}
      {isFetchingNextPage && <SkeletonList count={5} />}
      {/* Sentinel — always rendered so observer never loses its target */}
      <div ref={sentinelRef} aria-hidden="true" style={{ height: 1 }} />
    </ul>
  );
}
```

---

## Cloudflare Worker — Cursor Pagination Endpoint

```ts
// workers/api/tracks.ts
import type { D1Database } from '@cloudflare/workers-types';

interface Env { DB: D1Database; }

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url  = new URL(request.url);
    const cursor = url.searchParams.get('cursor');   // last seen track id
    const limit  = Math.min(Number(url.searchParams.get('limit') ?? 20), 50);

    const result = await env.DB
      .prepare(
        cursor
          ? `SELECT id, title, artist, created_at
             FROM tracks
             WHERE id < ?
             ORDER BY id DESC
             LIMIT ?`
          : `SELECT id, title, artist, created_at
             FROM tracks
             ORDER BY id DESC
             LIMIT ?`,
      )
      .bind(...(cursor ? [cursor, limit] : [limit]))
      .all();

    const tracks = result.results;
    const nextCursor = tracks.length === limit
      ? tracks[tracks.length - 1]?.id ?? null
      : null;

    return Response.json({ tracks, nextCursor });
  },
};
```

---

## D1 Keyset vs OFFSET Pagination

| Metric | OFFSET-based | Keyset (cursor) |
|---|---|---|
| Page 1 latency | ~10 ms | ~10 ms |
| Page 50 latency | ~500 ms (full scan) | ~10 ms (index seek) |
| Consistency | No — rows can shift | Yes — stable cursor |
| Implementation | Simple | Requires sortable key |
| Works with D1 | Yes | Yes |

D1 uses SQLite under the hood. An index on the cursor column is mandatory:

```sql
-- migration: 0001_create_tracks.sql
CREATE TABLE tracks (
  id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
  title       TEXT NOT NULL,
  artist      TEXT NOT NULL,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Keyset queries filter on id — index is required for performance
CREATE INDEX idx_tracks_id_desc ON tracks (id DESC);
```

---

## Skeleton Loading Strategy

Do not unmount skeletons the moment data arrives. A fade-out prevents the jarring jump.

```tsx
// components/SkeletonList.tsx
export function SkeletonList({ count }: { count: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <li
          key={i}
          className="skeleton-row"
          aria-busy="true"
          aria-label="Loading track"
        />
      ))}
    </>
  );
}
```

```css
/* styles/skeleton.css */
.skeleton-row {
  height: 64px;
  border-radius: 8px;
  background: linear-gradient(
    90deg,
    var(--color-surface-2) 25%,
    var(--color-surface-3) 50%,
    var(--color-surface-2) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}

@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Respect prefers-reduced-motion */
@media (prefers-reduced-motion: reduce) {
  .skeleton-row { animation: none; }
}
```

---

## Anti-patterns

- **`threshold: 0`** — rounding bug in iOS Safari ≤15; always use `0.01`.
- **Disconnecting + re-observing the sentinel on every render** — causes missed
  callbacks; keep the observer alive and use a stable ref.
- **`OFFSET n LIMIT m` in D1** — full table scan past first few pages; use keyset.
- **Rendering skeletons only while `isFetchingNextPage`** — they flash off before
  list items paint; add a minimum display duration or transition.
- **Using `window.scrollY` polling** instead of IntersectionObserver — blocks main
  thread, drains battery on mobile.

---

## Gotchas

- iOS Safari's virtual keyboard reduces `window.innerHeight` but not `document.body.scrollHeight`.
  A sentinel positioned relative to the bottom of the viewport can end up inside the
  keyboard rect and never intersect. Use a fixed `rootMargin` of `200px` to trigger
  early enough.
- D1 has a maximum of 1000 bound parameters per query. Keyset pagination with a single
  cursor avoids this entirely.
- `useInfiniteQuery` (TanStack Query) accumulates pages in memory. On feeds with many
  pages, consider windowing the rendered list with `react-virtual`.
- Cloudflare D1 is eventually consistent during replication. A cursor pointing to an id
  that hasn't propagated to all replicas may return 0 rows — handle the empty array case.

---

## Verification

```bash
# 1. Confirm index exists in D1
npx wrangler d1 execute example project-db --command \
  "EXPLAIN QUERY PLAN SELECT id FROM tracks WHERE id < 'abc' ORDER BY id DESC LIMIT 20;"
# Look for "SEARCH tracks USING INDEX idx_tracks_id_desc" in output

# 2. Simulate fast scroll in DevTools
# Chrome DevTools > Performance > record while scroll-clicking past sentinel

# 3. Test on real iOS Safari — use Safari Web Inspector + USB to check console
# Confirm no double fetches appear in the Network tab

# 4. CLS audit — skeletons should not shift layout on resolve
npx lighthouse https://example.com/feed --form-factor mobile \
  --only-audits=cumulative-layout-shift

# 5. Verify cursor pagination response shape
curl "https://example.com/api/tracks?limit=5" | jq '{nextCursor: .nextCursor, count: (.tracks | length)}'
```

---

## Related

- `browser-intersection-observer.md`
- `infinite-scroll-pagination-ux.md`
- `skeleton-screens-loading-states.md`
- `react-virtual-list.md`
- `html-web-vitals-cls.md`
- `touch-events-passive-listeners-mobile-scroll.md`

## Sources

- IntersectionObserver MDN — https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- iOS Safari IntersectionObserver bugs — https://bugs.webkit.org/show_bug.cgi?id=219770
- Keyset pagination — https://use-the-index-luke.com/no-offset
- TanStack Query useInfiniteQuery — https://tanstack.com/query/latest/docs/framework/react/reference/useInfiniteQuery
