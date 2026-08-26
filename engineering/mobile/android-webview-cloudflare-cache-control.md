# Android WebView Cloudflare Cache-Control Disparity

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

API responses served through Cloudflare Workers are stale inside an Android WebView (Capacitor
shell) even after the Worker or R2 object is updated. The `Cache-Control` headers set by the
Worker are respected inconsistently: WebView returns a cached version while an OkHttp client
(e.g., native Retrofit layer) fetches fresh content. The PWA Cache API (`caches.open(...)`) also
serves stale data independently of HTTP headers.

## Context

Android WebView uses a two-layer cache: the HTTP cache (shared with Chrome on pre-API-33 builds,
app-private on API 33+) and the PWA Cache Storage via the Service Worker Cache API. Cloudflare's
CDN adds its own `CF-Cache-Status` layer. These three caches can independently serve stale content.

The example project Capacitor shell uses `WebView.loadUrl()` backed by a custom `WebViewClient` and a
Service Worker for offline-first behaviour. OkHttp is used for native image uploads. The result is
four cache participants that must agree on freshness.

## Cache Participant Map

```
Request path (Capacitor / Android WebView)
  |
  +-- [1] Service Worker Cache API (PWA layer, app-controlled)
  |        Cache-Control ignored; freshness is script-defined
  |
  +-- [2] WebView HTTP Cache (CacheMode setting, API 33+ private)
  |        Obeys Cache-Control: max-age, s-maxage, no-store
  |
  +-- [3] Cloudflare Edge Cache (CF-Cache-Status header)
  |        Obeys Cache-Control: s-maxage, no-cache, private
  |
  +-- [4] Worker Response (origin)
           Your code; sets the authoritative headers
```

## Correct Cache-Control Headers per Resource Type

```
+----------------------------+------------------------------------------+----------------------------+
| Resource type              | Recommended Cache-Control                | CF behaviour               |
+----------------------------+------------------------------------------+----------------------------+
| Auth / session endpoints   | no-store, no-cache                       | Bypassed (BYPASS status)   |
| User feed (anon, paginated)| public, s-maxage=10, stale-while-revalidate=30 | Cached at edge        |
| Static media (R2 images)   | public, max-age=31536000, immutable      | Cached at edge + CDN       |
| Profile data               | private, max-age=0, must-revalidate      | Bypassed (PRIVATE)         |
| Turnstile / challenge page | no-store                                 | Bypassed                   |
+----------------------------+------------------------------------------+----------------------------+
```

## Worker Header Setup

```typescript
// worker/src/middleware/cache-headers.ts
export type CacheProfile = "auth" | "feed" | "media" | "profile" | "challenge";

const PROFILES: Record<CacheProfile, string> = {
  auth: "no-store, no-cache",
  feed: "public, s-maxage=10, stale-while-revalidate=30",
  media: "public, max-age=31536000, immutable",
  profile: "private, max-age=0, must-revalidate",
  challenge: "no-store",
};

export function applyCacheProfile(
  response: Response,
  profile: CacheProfile
): Response {
  const headers = new Headers(response.headers);
  headers.set("Cache-Control", PROFILES[profile]);
  // Cloudflare respects Surrogate-Control for edge only, not returned to client
  if (profile === "feed") {
    headers.set("Surrogate-Control", "public, s-maxage=10");
    headers.set("Vary", "Accept-Encoding, CF-Device-Type");
  }
  return new Response(response.body, { ...response, headers });
}
```

## Android WebView Cache Mode Configuration (Capacitor)

```typescript
// capacitor.config.ts
import { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "app.example project.example project",
  webDir: "dist",
  android: {
    // LOAD_DEFAULT: use HTTP headers — DO NOT use LOAD_CACHE_ELSE_NETWORK
    // which ignores max-age and serves stale for the entire session
    webContentsDebuggingEnabled: true,
  },
};
```

```java
// android/app/src/main/java/app/example project/example project/MainActivity.java
import android.webkit.WebSettings;

WebSettings settings = webView.getSettings();
// Honour HTTP Cache-Control headers — do NOT override with LOAD_CACHE_ELSE_NETWORK
settings.setCacheMode(WebSettings.LOAD_DEFAULT);
// Disable mixed-content (required for Cloudflare HTTPS-only)
settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
```

## Bypassing the WebView HTTP Cache for Dynamic Requests

```typescript
// src/lib/api-client.ts
export async function apiFetch(
  path: string,
  init: RequestInit = {}
): Promise<Response> {
  // Add cache-busting header to bypass WebView HTTP cache on dynamic endpoints
  const headers = new Headers(init.headers);
  headers.set("Cache-Control", "no-cache");
  headers.set("Pragma", "no-cache"); // older WebView compat

  return fetch(`https://api.example.com${path}`, {
    ...init,
    headers,
    cache: "no-cache", // Fetch API hint
  });
}
```

## Cloudflare Cache Key Customisation

Cloudflare's default cache key is `method + host + path`. For the example project anonymous social feed,
device type must be part of the key to avoid serving mobile layout to desktop and vice versa:

```typescript
// worker/src/middleware/cache-key.ts
export function buildCacheKey(request: Request): Request {
  const url = new URL(request.url);
  // Append device bucket so CF caches mobile/desktop variants separately
  const cfDeviceType = (request as any).cf?.deviceType ?? "desktop"; // "mobile" | "desktop" | "tablet"
  url.searchParams.set("_cdk", cfDeviceType);
  return new Request(url.toString(), request);
}

export async function serveWithCacheKey(
  request: Request,
  env: Env,
  handler: (r: Request, e: Env) => Promise<Response>
): Promise<Response> {
  const cacheKey = buildCacheKey(request);
  const cache = caches.default;
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  const response = await handler(request, env);
  if (response.ok) {
    await cache.put(cacheKey, response.clone());
  }
  return response;
}
```

## OkHttp vs WebView Cache Disparity Debug

```kotlin
// android/app/src/main/java/app/example project/example project/network/WaspOkHttp.kt
val client = OkHttpClient.Builder()
    .cache(Cache(File(context.cacheDir, "okhttp_cache"), 10L * 1024 * 1024)) // 10 MB
    .addNetworkInterceptor { chain ->
        val response = chain.proceed(chain.request())
        // Log CF cache status for comparison with WebView
        val cfStatus = response.header("CF-Cache-Status") ?: "MISS"
        Log.d("WaspCache", "CF-Cache-Status: $cfStatus for ${chain.request().url}")
        response
    }
    .build()
```

## Anti-patterns

- Using `WebSettings.LOAD_CACHE_ELSE_NETWORK` — ignores `max-age` and serves cached data for the
  entire WebView lifecycle regardless of staleness.
- Setting `Cache-Control: public` on authenticated endpoints — Cloudflare will cache the response
  and potentially serve one user's data to another.
- Using `s-maxage` without also setting `max-age` — OkHttp and WebView fall back to `max-age` when
  `s-maxage` is absent; omitting `max-age` causes them to calculate heuristic freshness.
- Writing to PWA Cache Storage from a Service Worker without also purging on Worker deploy — the
  Cache API is entirely separate from the HTTP cache and ignores `Cache-Control` headers.
- Relying on `CF-Cache-Status: HIT` in responses seen by mobile clients — CF adds this header after
  the edge serves the cached copy, but WebView may still return its own local cache hit first.

## Gotchas

- On Android API 33+, the WebView cache is app-private and no longer shared with Chrome. Clearing
  Chrome's cache from device settings does NOT clear the Capacitor app's WebView cache.
- `stale-while-revalidate` is honoured by Cloudflare's edge but is NOT honoured by Android
  WebView's HTTP cache implementation before Chrome 80 (API 29 era devices).
- The `Vary: Cookie` directive causes Cloudflare to BYPASS the cache entirely — avoid it on public
  feed endpoints; use cache key customisation instead.
- Cloudflare Free/Pro plans have a minimum TTL of 1 hour for static assets regardless of
  `Cache-Control: max-age` values below 3600.
- `immutable` is not respected by Android WebView before Chromium 124 build; include `max-age` as
  the fallback freshness signal.

## Verification

```bash
# Check CF-Cache-Status progression (MISS -> HIT)
for i in 1 2 3; do
  curl -si https://api.example.com/v1/feed \
    -H "CF-Device-Type: mobile" | grep -E "CF-Cache-Status|Cache-Control|Age"
  echo "---"
done

# Purge by tag (requires Cloudflare Pro+)
curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"tags":["feed","mobile"]}'

# WebView cache inspection — adb shell
adb shell run-as app.example project.example project ls -la cache/WebView/Default/HTTP\ Cache/Cache_Data/
```

## Related

- `android-webview-cloudflare-security-headers.md`
- `mobile-network-resilience-cloudflare-workers.md`
- `pwa-offline-caching-strategies.md`
- `mobile-image-caching-patterns.md`
- `offline-first-worker-api-resilience.md`

## Sources

- https://developers.cloudflare.com/cache/concepts/cache-control/
- https://developers.cloudflare.com/cache/how-to/cache-keys/
- https://developer.android.com/reference/android/webkit/WebSettings#setCacheMode(int)
- https://square.github.io/okhttp/features/caching/
- https://web.dev/articles/stale-while-revalidate
