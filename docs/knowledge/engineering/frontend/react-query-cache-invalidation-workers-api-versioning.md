# React Query Cache Invalidation with Workers API Versioning

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

After deploying a new version of a Cloudflare Worker that changes a response shape, previously
cached React Query data persists in clients' memory and (if you use `persistQueryClient`) in
`localStorage` or `IndexedDB`. Users see stale, broken UI until they manually refresh or the
cache TTL expires. The problem compounds on mobile where tabs stay backgrounded for hours.

---

## Context

Cloudflare Pages + Workers creates an asymmetric deployment model: the Worker (edge function)
can be rolled out atomically across all PoPs in seconds, but the React Query in-memory cache
lives inside every client browser independently. When a Worker's response contract changes
(field renames, nested restructures, enum changes), clients holding old cache entries will
render with mismatched data until invalidation fires.

React Query's `staleTime` / `gcTime` defaults are `0` / `5 minutes`, meaning data refetches on
window focus, but the refetch still merges into the same cache key — it does not purge the
old shape from the in-memory store. With `persistQueryClient` the stale shape can survive
browser restarts.

Three layers need versioning:
1. The **Worker API response** (semver or hash-based)
2. The **React Query cache key** (include a version token)
3. The **persisted cache** (bust the storage key on version change)

---

## Section 1 — Embedding a Version Token in Worker Responses

The cleanest strategy is to embed a short version token in every Worker response, either as
an HTTP header or inside the JSON envelope.

```ts
// worker/src/index.ts
const API_VERSION = 'v3'; // bump this with breaking changes

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const data = await getProducts(env);
    return Response.json(
      { version: API_VERSION, data },
      {
        headers: {
          'X-API-Version': API_VERSION,
          'Cache-Control': 'no-store', // prevent Cloudflare edge cache from staling version
        },
      }
    );
  },
};
```

On the client, read the version and store it in a React context or a Zustand atom so every
query subscriber can compare against the "current known version."

```ts
// lib/api-version.ts
export const API_VERSION_KEY = 'api-version';

export function getStoredVersion(): string | null {
  try {
    return localStorage.getItem(API_VERSION_KEY);
  } catch {
    return null;
  }
}

export function setStoredVersion(v: string) {
  try {
    localStorage.setItem(API_VERSION_KEY, v);
  } catch {}
}
```

---

## Section 2 — Version-Aware Query Keys

React Query's cache key is a serialisable array. Appending the API version makes every
breaking-change deploy produce a distinct key, so stale data simply becomes an orphaned
cache entry and the new key starts empty.

```ts
// hooks/use-products.ts
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApiVersion } from '@/lib/api-version-context';

export function useProducts(categoryId: string) {
  const { version } = useApiVersion();         // e.g. 'v3'
  const qc = useQueryClient();

  return useQuery({
    // ↓ include version in the key
    queryKey: ['products', categoryId, { apiV: version }],
    queryFn: async ({ signal }) => {
      const res = await fetch(`/api/products?category=${categoryId}`, { signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const envelope = await res.json();

      // detect version drift mid-session and invalidate everything
      if (envelope.version && envelope.version !== version) {
        setStoredVersion(envelope.version);
        qc.invalidateQueries(); // flush all keys, new version will repopulate
      }

      return envelope.data;
    },
    staleTime: 60_000,   // 1 min
    gcTime: 5 * 60_000,  // 5 min
  });
}
```

---

## Section 3 — Busting the Persisted Cache on Version Change

`persistQueryClient` serialises the entire in-memory cache to `localStorage` (default) or
`IndexedDB`. Without a buster, a version bump still loads the old persisted cache and
renders it before the first refetch completes.

```ts
// lib/query-persister.ts
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister';
import { persistQueryClient } from '@tanstack/react-query-persist-client';
import { QueryClient } from '@tanstack/react-query';

const PERSIST_KEY_PREFIX = 'rq-cache';
const CURRENT_VERSION = 'v3'; // keep in sync with Worker API_VERSION

export function createPersistedQueryClient() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { staleTime: 60_000 },
    },
  });

  const persister = createSyncStoragePersister({
    storage: typeof window !== 'undefined' ? window.localStorage : undefined,
    // Changing this key purges all persisted data for old versions
    key: `${PERSIST_KEY_PREFIX}-${CURRENT_VERSION}`,
  });

  persistQueryClient({
    queryClient: qc,
    persister,
    maxAge: 24 * 60 * 60 * 1000, // 24 h
  });

  return qc;
}
```

On next deploy bump `CURRENT_VERSION` to `v4`. The old `rq-cache-v3` key in `localStorage`
becomes orphaned and is never read again. Old entries accumulate until `localStorage` quota
is approached — add a cleanup sweep on app init:

```ts
// app/layout.tsx  (client component initialiser)
function purgeStalePersistKeys(currentKey: string) {
  if (typeof localStorage === 'undefined') return;
  const PREFIX = 'rq-cache-';
  for (const k of Object.keys(localStorage)) {
    if (k.startsWith(PREFIX) && k !== currentKey) {
      localStorage.removeItem(k);
    }
  }
}
```

---

## Section 4 — Broadcasting Version Changes Across Tabs

On mobile, users typically keep multiple tabs open. A version bump detected in one tab should
propagate to siblings without requiring a reload.

```ts
// lib/version-broadcast.ts
const CHANNEL_NAME = 'api-version-sync';

export function broadcastVersionChange(newVersion: string) {
  try {
    const bc = new BroadcastChannel(CHANNEL_NAME);
    bc.postMessage({ type: 'VERSION_CHANGE', version: newVersion });
    bc.close();
  } catch {}
}

export function listenForVersionChanges(
  onNewVersion: (v: string) => void
): () => void {
  let bc: BroadcastChannel | null = null;
  try {
    bc = new BroadcastChannel(CHANNEL_NAME);
    bc.onmessage = (e) => {
      if (e.data?.type === 'VERSION_CHANGE') {
        onNewVersion(e.data.version);
      }
    };
  } catch {}
  return () => bc?.close();
}
```

Wire it into a root `useEffect` in the QueryClientProvider wrapper:

```tsx
// providers/query-provider.tsx
'use client';

import { useEffect } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createPersistedQueryClient } from '@/lib/query-persister';
import { listenForVersionChanges } from '@/lib/version-broadcast';
import { ApiVersionProvider } from '@/lib/api-version-context';

const qc = createPersistedQueryClient();

export function QueryProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    const unsub = listenForVersionChanges(() => {
      qc.invalidateQueries();   // flush and refetch in this tab too
    });
    return unsub;
  }, []);

  return (
    <QueryClientProvider client={qc}>
      <ApiVersionProvider>
        {children}
      </ApiVersionProvider>
    </QueryClientProvider>
  );
}
```

---

## Anti-patterns

- **Cache key without version**: `['products', id]` will happily serve v2 data to v3 code.
- **Invalidating only specific keys**: a Worker deploy may touch multiple endpoints; full
  invalidation is safer unless you track per-endpoint versions.
- **Storing the version only in memory**: a page reload would lose it; always hydrate from
  the response header on first mount.
- **Using `refetchOnWindowFocus: false` globally**: suppresses the natural invalidation
  signal that catches stale data when a user switches back to the tab after a deploy.

---

## Gotchas

- `BroadcastChannel` is unavailable in Safari < 15.4 and all iOS Safari < 15.4. Feature-
  detect before constructing; the `try/catch` above handles this gracefully.
- `persistQueryClient` is **not** SSR-safe — always gate with `typeof window !== 'undefined'`
  or place the persister setup inside a `useEffect`.
- Cloudflare Workers deployments are not atomic to every PoP simultaneously. During rollout
  (< 60 seconds), some clients may hit v2 Workers and some v3 Workers from the same tab.
  Design your response envelope to be backwards-compatible for at least one version to avoid
  thrashing cache invalidation.
- If you use Cloudflare's **smart placement** or **Durable Objects**, the version token
  should come from `env.API_VERSION` (a binding variable set in `wrangler.toml`) rather than
  being hardcoded, so it's consistent across instances.

---

## Verification

1. Deploy a Worker with `API_VERSION = 'v2'`. Load the app, confirm `rq-cache-v2` key exists
   in DevTools → Application → localStorage.
2. Bump to `v2.1` (breaking schema change). Reload; confirm `rq-cache-v2.1` is created and
   `rq-cache-v2` is removed by the cleanup sweep.
3. Open two tabs. In tab 1, trigger a query that detects the version bump. Confirm tab 2's
   network panel shows new fetches within a second (BroadcastChannel delivery).
4. On an iOS device, background the tab for 10 minutes, return, and confirm data is fresh.

---

## Related

- `react-query-patterns.md`
- `react-query-server-state-management.md`
- `optimistic-ui-updates-rollback.md`
- `pwa-service-worker-cloudflare-pages.md`
- `browser-broadcastchannel-cross-tab-coordination.md`

---

## Sources

- TanStack Query docs — Cache & Invalidation: https://tanstack.com/query/latest/docs/framework/react/guides/invalidations-from-mutations
- TanStack Query persist client: https://tanstack.com/query/latest/docs/framework/react/plugins/persistQueryClient
- Cloudflare Workers versioning: https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- BroadcastChannel MDN: https://developer.mozilla.org/en-US/docs/Web/API/BroadcastChannel
