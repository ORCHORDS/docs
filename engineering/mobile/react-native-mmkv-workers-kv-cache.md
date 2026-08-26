# React Native MMKV as Local Cache Layer Backed by Cloudflare KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

App repeatedly hits the Cloudflare Workers API for quasi-static data (feature flags, user preferences, catalogue slugs). Cold-start latency is 300–600 ms on each request. You want a two-tier cache: ultra-fast synchronous reads from MMKV (SQLite-backed key-value store on device) with a background refresh from Cloudflare KV, without blocking the render thread.

## Context

`react-native-mmkv` (by Marc Rousavy) provides synchronous, JSI-based storage roughly 30× faster than AsyncStorage. Cloudflare KV is a globally replicated key-value store with sub-millisecond reads at the edge. The combination gives you a stale-while-revalidate cache with no UI blocking: the UI reads MMKV instantly and the Worker silently refreshes from KV in the background.

Architecture:

```
Mobile app → Workers edge → Cloudflare KV (authoritative)
     ↑              ↓
   MMKV         (namespace)
 (local cache)
```

Cloudflare Workers add a `Cache-Control` and `X-KV-TTL` header so the mobile layer knows when to invalidate.

## Workers KV Read Endpoint

```typescript
// workers/kv-proxy/index.ts
export interface Env {
  APP_CACHE: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.searchParams.get("key");

    if (!key) {
      return new Response(JSON.stringify({ error: "missing key" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const { value, metadata } = await env.APP_CACHE.getWithMetadata<{
      ttl: number;
      version: string;
    }>(key, { type: "json" });

    if (value === null) {
      return new Response(JSON.stringify({ error: "not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    const ttl = metadata?.ttl ?? 300;
    return new Response(JSON.stringify({ data: value, version: metadata?.version }), {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": `public, max-age=${ttl}`,
        "X-KV-TTL": String(ttl),
        "X-KV-Version": metadata?.version ?? "1",
      },
    });
  },
};
```

## Workers KV Write Endpoint (Admin)

```typescript
// workers/kv-proxy/write.ts – protected by an Authorization header check
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "PUT") return new Response("Method Not Allowed", { status: 405 });

    const authHeader = request.headers.get("Authorization");
    if (authHeader !== `Bearer ${(env as any).ADMIN_SECRET}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    const body = await request.json<{ key: string; value: unknown; ttlSeconds: number }>();
    await env.APP_CACHE.put(body.key, JSON.stringify(body.value), {
      expirationTtl: body.ttlSeconds,
      metadata: { ttl: body.ttlSeconds, version: Date.now().toString() },
    });

    return new Response(JSON.stringify({ ok: true }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## React Native MMKV Cache Client

```typescript
// src/cache/kvCache.ts
import { MMKV } from "react-native-mmkv";

const storage = new MMKV({ id: "kv-cache" });
const WORKERS_BASE = "https://cache.example.com";

interface CacheEntry<T> {
  data: T;
  version: string;
  expiresAt: number; // epoch ms
}

export async function getCached<T>(key: string): Promise<T | null> {
  const raw = storage.getString(key);
  if (raw) {
    const entry = JSON.parse(raw) as CacheEntry<T>;
    // Return stale value immediately; refresh happens in background
    refreshInBackground(key);
    return entry.data;
  }

  // Cache miss — must fetch synchronously
  return fetchAndStore<T>(key);
}

async function fetchAndStore<T>(key: string): Promise<T | null> {
  try {
    const res = await fetch(`${WORKERS_BASE}/kv?key=<redacted-secret>
    if (!res.ok) return null;

    const ttl = Number(res.headers.get("X-KV-TTL") ?? "300");
    const version = res.headers.get("X-KV-Version") ?? "1";
    const json = await res.json<{ data: T }>();

    const entry: CacheEntry<T> = {
      data: json.data,
      version,
      expiresAt: Date.now() + ttl * 1000,
    };
    storage.set(key, JSON.stringify(entry));
    return json.data;
  } catch {
    return null;
  }
}

function refreshInBackground(key: string): void {
  // Fire-and-forget; never awaited on the render path
  fetchAndStore(key).catch(() => {/* silent */});
}

export function invalidate(key: string): void {
  storage.delete(key);
}
```

## React Hook Integration

```typescript
// src/hooks/useKVCache.ts
import { useEffect, useState } from "react";
import { getCached } from "../cache/kvCache";

export function useKVCache<T>(key: string): { data: T | null; loading: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getCached<T>(key).then((value) => {
      if (!cancelled) {
        setData(value);
        setLoading(false);
      }
    });
    return () => { cancelled = true; };
  }, [key]);

  return { data, loading };
}

// Usage in a component:
// const { data: flags } = useKVCache<FeatureFlags>("feature-flags:v2");
```

## Batch Prefetch on App Foreground

```typescript
// src/cache/prefetch.ts
import { AppState, AppStateStatus } from "react-native";
import { getCached } from "./kvCache";

const PREFETCH_KEYS = ["feature-flags:v2", "config:theme", "catalogue:slugs"];

export function registerPrefetchOnForeground(): () => void {
  const handler = (state: AppStateStatus) => {
    if (state === "active") {
      PREFETCH_KEYS.forEach((k) => getCached(k));
    }
  };
  const sub = AppState.addEventListener("change", handler);
  return () => sub.remove();
}
```

## Anti-patterns

- **Blocking the JS thread on fetch**: never `await getCached()` during render; call it in `useEffect` or before navigation.
- **Storing large blobs in MMKV**: MMKV is optimised for small values (< 64 KB). Push large payloads to R2 and store only a URL in KV/MMKV.
- **Identical TTL for all keys**: short-lived keys (e.g., prices) share a namespace with long-lived keys (e.g., static config). Set `ttlSeconds` per-key on the Worker write endpoint.
- **No version check on stale data**: without `X-KV-Version`, you cannot detect a forced invalidation push from the backend. Always store and compare versions.

## Gotchas

- `react-native-mmkv` requires Hermes on RN 0.71+; the JSI bridge is not available in Expo Go — use a custom dev client.
- Cloudflare KV has eventual consistency: a freshly written key may not be visible at every edge PoP for up to 60 seconds. Do not use KV for session tokens or payment state.
- MMKV persists across app updates on Android unless the user clears data. Bump the cache key version (e.g., `feature-flags:v3`) after schema changes.
- The Workers free tier has a 100,000 KV read/day limit. Batch reads with a `?keys=a,b,c` multi-get endpoint to stay within quota on high-MAU apps.

## Verification

```bash
# 1. Seed a KV value via the admin endpoint
curl -X PUT https://cache.example.com/kv/write \
  -H "Authorization: Bearer $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"key":"feature-flags:v2","value":{"darkMode":true},"ttlSeconds":600}'

# 2. Read it back through the proxy
curl https://cache.example.com/kv?key=<redacted-secret>

# 3. Confirm MMKV is populated in Metro logs
# Log getCached() result on first render; second render should show instant sync read.
```

## Related

- `react-native-mmkv-storage.md`
- `cloudflare-kv-read-latency-mobile-highlatency-vs-desktop.md`
- `mobile-feature-flags-remote-config.md`
- `react-native-workers-background-fetch-cron-sync.md`

## Sources

- https://github.com/mrousavy/react-native-mmkv
- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
