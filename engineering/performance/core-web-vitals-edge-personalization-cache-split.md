# Core Web Vitals: Edge Personalization Without Killing Cache Hit Rate

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Personalised page variants (logged-in user name, cart count, geo-specific pricing) prevent full-page HTML caching, causing every request to hit the origin and degrading LCP and TTFB for authenticated users. Splitting personalisation to the edge with a cached shell resolves the conflict.

## Context
Core Web Vitals — especially LCP and TTFB — depend heavily on how fast the first byte of HTML arrives. Full-page dynamic rendering for personalised content defeats CDN caching entirely. The edge personalization pattern splits the page into a cacheable shell (HTML structure, CSS, JS, hero image) and a tiny personalisation payload fetched via a lightweight edge Worker or inline script. The shell caches with a long TTL; only the personalisation API call is uncached. LCP fires on the hero image (cached shell), which is fast; personalised content fills in asynchronously without blocking LCP.

## HTML Shell Caching at the Edge

Serve the page skeleton from cache with a long TTL, stripping cookies and auth headers to maximise cache key breadth:

```typescript
interface Env {
  ORIGIN_URL: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Only cache HTML — other assets handled separately
    const isHtml =
      request.headers.get("accept")?.includes("text/html") &&
      (url.pathname === "/" || url.pathname.endsWith(".html") || !url.pathname.includes("."));

    if (!isHtml) return fetch(request);

    // Build a cache key that ignores auth cookies to maximise hit rate
    const cacheKey = new Request(url.origin + url.pathname, {
      method: "GET",
      headers: {
        // Preserve only non-personalised Vary dimensions
        "accept-language": request.headers.get("accept-language") ?? "en",
        "accept-encoding": request.headers.get("accept-encoding") ?? "gzip",
      },
    });

    const cache = caches.default;
    const cached = await cache.match(cacheKey);
    if (cached) {
      return new Response(cached.body, {
        status: cached.status,
        headers: { ...Object.fromEntries(cached.headers), "x-cache": "HIT" },
      });
    }

    // Fetch shell from origin — origin must NOT include personalised content
    const shell = await fetch(env.ORIGIN_URL + url.pathname, {
      headers: { "x-edge-request": "shell-only" },
    });

    const shellResponse = new Response(shell.body, {
      status: shell.status,
      headers: {
        "content-type": "text/html; charset=utf-8",
        "cache-control": "public, max-age=300, stale-while-revalidate=60",
        "x-cache": "MISS",
      },
    });

    ctx.waitUntil(cache.put(cacheKey, shellResponse.clone()));
    return shellResponse;
  },
};
```

## Personalisation API at the Edge with KV

Serve personalised data from a lightweight edge endpoint backed by KV, avoiding origin calls:

```typescript
interface Env {
  USER_KV: KVNamespace;
}

interface UserPersonalisation {
  name: string;
  cartCount: number;
  currency: string;
  priceTier: "A" | "B" | "C";
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== "/_edge/me") return new Response("Not Found", { status: 404 });

    const sessionToken = parseCookieToken(request.headers.get("cookie") ?? "");
    if (!sessionToken) {
      return Response.json({ name: null, cartCount: 0, currency: "USD", priceTier: "A" });
    }

    const data = await env.USER_KV.get<UserPersonalisation>(
      `session:${sessionToken}`,
      { type: "json", cacheTtl: 30 },
    );

    return Response.json(data ?? { name: null, cartCount: 0, currency: "USD", priceTier: "A" }, {
      headers: {
        "cache-control": "private, no-store",
        "content-type": "application/json",
      },
    });
  },
};

function parseCookieToken(cookie: string): string | null {
  const match = /(?:^|;\s*)sess=([^;]+)/.exec(cookie);
  return match?.[1] ?? null;
}
```

## Client-side Personalisation Injection (No LCP Impact)

Inject personalisation after LCP using `requestIdleCallback` so the main thread is not blocked during paint:

```html
<!-- In the cached HTML shell — add to <head> -->
<script>
  // Fetch personalisation data without blocking LCP
  const personalisationPromise = fetch("/_edge/me", { credentials: "include" })
    .then((r) => r.json())
    .catch(() => null);

  // Apply personalisation only after the page is idle
  function applyPersonalisation(data) {
    if (!data?.name) return;
    const el = document.getElementById("user-greeting");
    if (el) el.textContent = "Hi, " + data.name;
    const cart = document.getElementById("cart-count");
    if (cart && data.cartCount > 0) {
      cart.textContent = data.cartCount;
      cart.removeAttribute("hidden");
    }
  }

  if ("requestIdleCallback" in window) {
    personalisationPromise.then((data) =>
      requestIdleCallback(() => applyPersonalisation(data), { timeout: 2000 })
    );
  } else {
    personalisationPromise.then(applyPersonalisation);
  }
</script>
```

## Measuring LCP Impact Before and After

Instrument the cache-split pattern's effect on LCP with the Performance Observer:

```typescript
// In a Worker-served analytics endpoint — collect LCP from field data
interface RumPayload {
  lcp: number;
  cacheHit: boolean;
  pathname: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const payload = await request.json<RumPayload>();

    await env.ANALYTICS.writeDataPoint({
      blobs: [payload.pathname, payload.cacheHit ? "hit" : "miss"],
      doubles: [payload.lcp],
      indexes: [payload.pathname],
    });

    return new Response(null, { status: 204 });
  },
};
```

```javascript
// Client: report LCP with cache status
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    if (entry.entryType === "largest-contentful-paint") {
      const cacheHit = document.querySelector("meta[name=x-cache]")?.content === "HIT";
      navigator.sendBeacon("/_rum/lcp", JSON.stringify({
        lcp: entry.startTime,
        cacheHit,
        pathname: location.pathname,
      }));
    }
  }
}).observe({ type: "largest-contentful-paint", buffered: true });
```

## Anti-patterns
- Varying the cache key on `Cookie` headers — this creates millions of cache variants, one per user, effectively defeating caching
- Blocking `DOMContentLoaded` with the personalisation fetch — this delays LCP by making the browser wait for personalised HTML
- Embedding auth tokens in the HTML shell — the shell is cached and shared across users; never include user-specific data in it
- Setting `Vary: Cookie` on the shell response — this forces the CDN to cache a copy per unique `Cookie` value

## Gotchas
- The `stale-while-revalidate` window means some users see 60-second-old HTML — acceptable for structural content but not for prices; personalise prices client-side
- KV `cacheTtl` of 30 s means session data updates (logout, cart change) may be visible up to 30 s after the event — inform UX team
- `requestIdleCallback` may not fire for up to 5 seconds on heavily loaded pages; use the `timeout` option to force execution

## Verification
1. Run Lighthouse on the personalised page before and after — LCP should improve by 200–500 ms when the shell is cached
2. Check `x-cache: HIT` rate in Cloudflare Analytics; target > 80% for HTML shell requests
3. Use WebPageTest with "logged in" scripting to confirm personalisation appears without delaying LCP paint
4. Verify `CF-Cache-Status` is `HIT` on repeat visits with different cookies — confirms cookie stripping in cache key

## Related
- [lcp-optimization.md](lcp-optimization.md)
- [ttfb-optimization.md](ttfb-optimization.md)
- [kv-read-performance.md](kv-read-performance.md)
- [core-web-vitals-overview.md](core-web-vitals-overview.md)
- [edge-caching-patterns.md](edge-caching-patterns.md)
- [critical-rendering-path.md](critical-rendering-path.md)

## Sources
- Cloudflare Docs: Cache Keys — https://developers.cloudflare.com/cache/how-to/cache-keys/
- web.dev: Personalization without sacrificing performance — https://web.dev/personalization/
- W3C: Largest Contentful Paint spec — https://w3c.github.io/largest-contentful-paint/
- MDN: requestIdleCallback — https://developer.mozilla.org/en-US/docs/Web/API/Window/requestIdleCallback
