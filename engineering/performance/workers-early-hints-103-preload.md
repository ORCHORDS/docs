# HTTP 103 Early Hints for Resource Preloading from Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Users on high-latency connections experience slow page renders because critical assets
(fonts, hero scripts, primary stylesheets) only begin downloading after the full HTML
response arrives. The browser sits idle while the Worker is building the page, wasting
hundreds of milliseconds that could be spent fetching known-necessary resources.

---

## Context

HTTP 103 Early Hints is a 1xx informational response defined in RFC 8297. The server
(or edge Worker) emits a lightweight response with `Link: <url>; rel=preload` headers
before the final 200 response is ready. Modern browsers (Chrome 103+, Firefox 120+,
Safari 17.2+) act on these hints immediately, initiating parallel fetches for critical
assets while the origin continues processing.

Cloudflare Workers can write a 103 response using the `Response` constructor with status
`103` on a `WritableStream`-backed connection, or — more practically — by returning an
early-hints response via the `fetch` event and then returning the real response. As of
2024, Cloudflare supports Early Hints natively at the edge for HTML pages, and Workers
can inject hint headers via `cf.html_rewrite` or by constructing a 103 before streaming
the body.

**Key tradeoffs vs HTTP/2 Server Push:**
- Early Hints do not push bytes; they only signal intent. The browser decides whether
  to fetch based on its cache. Push wastes bandwidth on already-cached resources.
- Early Hints work over HTTP/1.1 tunnels and HTTP/2 equally.
- Early Hints have zero risk of push-stream cancellation overhead.

---

## Solution

### 1. Emitting 103 Early Hints from a Worker

```typescript
// worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Resolve hint configuration for this route from KV (cached)
    const hints = await getRouteHints(url.pathname, env);

    // Build the 103 response — headers only, no body
    const earlyHints = new Response(null, {
      status: 103,
      headers: buildLinkHeaders(hints),
    });

    // In Cloudflare Workers the runtime handles flushing the 103
    // before the actual response when you return a 1xx response
    // using the `cf` extension. For full control, use a TransformStream.
    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();

    // Fire origin fetch in parallel with writing the early-hints preamble
    const originPromise = fetchFromOrigin(request, env);

    // Cloudflare-specific: attach cf.earlyHints to signal the runtime
    const response = new Response(readable, {
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
      // @ts-expect-error cf property not in base types
      cf: { earlyHints: buildLinkHeaders(hints) },
    });

    (async () => {
      const origin = await originPromise;
      const reader = origin.body!.getReader();
      while (true) {
        const { done, value } = await reader.read();
        if (done) { await writer.close(); break; }
        await writer.write(value);
      }
    })();

    return response;
  },
};
```

### 2. KV-cached hint configuration per route

```typescript
interface HintConfig {
  preloads: Array<{
    url: string;
    as: 'font' | 'script' | 'style' | 'image' | 'fetch';
    crossorigin?: boolean;
    fetchpriority?: 'high' | 'low' | 'auto';
  }>;
  ttl: number; // seconds
}

async function getRouteHints(pathname: string, env: Env): Promise<HintConfig> {
  // Normalize pathname to a config key
  const routeKey = normalizeRoute(pathname);
  const kvKey = `early-hints:${routeKey}`;

  // Check in-memory cache first (Worker isolate lifetime)
  if (hintCache.has(kvKey)) return hintCache.get(kvKey)!;

  const raw = await env.CONFIG_KV.get(kvKey, { type: 'json' }) as HintConfig | null;
  const config: HintConfig = raw ?? DEFAULT_HINTS;

  // Cache for isolate lifetime to avoid KV latency on every request
  hintCache.set(kvKey, config);
  return config;
}

const hintCache = new Map<string, HintConfig>();

const DEFAULT_HINTS: HintConfig = {
  preloads: [
    { url: '/fonts/inter-var.woff2', as: 'font', crossorigin: true },
    { url: '/css/critical.css', as: 'style' },
    { url: '/js/main.js', as: 'script', fetchpriority: 'high' },
  ],
  ttl: 3600,
};

function normalizeRoute(pathname: string): string {
  // Map /products/123 -> /products/:id
  return pathname.replace(/\/\d+/g, '/:id').replace(/\/$/, '') || '/';
}

function buildLinkHeaders(config: HintConfig): Record<string, string> {
  const links = config.preloads.map((p) => {
    let header = `<${p.url}>; rel=preload; as=${p.as}`;
    if (p.crossorigin) header += '; crossorigin';
    if (p.fetchpriority) header += `; fetchpriority=${p.fetchpriority}`;
    return header;
  });
  return { Link: links.join(', ') };
}
```

### 3. Storing hint config in KV

```typescript
// scripts/update-hints.ts — run via Wrangler CLI or a cron Worker
async function publishHintConfig(env: Env) {
  const configs: Record<string, HintConfig> = {
    '/': {
      preloads: [
        { url: '/fonts/inter-var.woff2', as: 'font', crossorigin: true },
        { url: '/css/critical.css', as: 'style' },
        { url: '/js/home-bundle.js', as: 'script', fetchpriority: 'high' },
        { url: '/images/hero.avif', as: 'image', fetchpriority: 'high' },
      ],
      ttl: 7200,
    },
    '/products/:id': {
      preloads: [
        { url: '/fonts/inter-var.woff2', as: 'font', crossorigin: true },
        { url: '/css/critical.css', as: 'style' },
        { url: '/js/product-bundle.js', as: 'script' },
      ],
      ttl: 3600,
    },
  };

  for (const [route, config] of Object.entries(configs)) {
    await env.CONFIG_KV.put(
      `early-hints:${route}`,
      JSON.stringify(config),
      { expirationTtl: config.ttl * 10 }, // KV TTL longer than hint TTL
    );
  }
}
```

### 4. Measuring LCP improvement via Timing-Allow-Origin

```typescript
function addTimingHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  // Allow RUM scripts to read resource timing for cross-origin assets
  headers.set('Timing-Allow-Origin', '*');
  // Server-Timing for worker processing phases
  headers.append('Server-Timing', 'hints;desc="early-hints-emitted";dur=0');
  return new Response(response.body, { ...response, headers });
}
```

---

## Implementation Details

- **103 status support**: Cloudflare's edge strips 1xx responses from HTTP/1.1 clients
  but forwards them to HTTP/2 and HTTP/3 clients. Verify your client supports it.
- **Asset URL stability**: Hint URLs must be stable (ideally content-hashed) so browsers
  can match them against cached entries. Avoid cache-busting query strings in hint URLs.
- **Font crossorigin**: Fonts loaded via `@font-face` require `crossorigin` on the hint
  to match the request mode. Omitting it causes a double fetch.
- **KV read latency**: A single `env.KV.get()` from a Cloudflare Worker averages 5–15 ms
  within the same region. In-isolate caching (module-scope `Map`) eliminates this after
  the first request per isolate.

---

## Anti-patterns

- **Hinting every asset**: Hint only truly critical render-blocking resources. Hinting
  20+ assets creates connection contention and may delay the LCP resource itself.
- **Hinting non-stable URLs**: Dynamic URLs (e.g., `/api/user?t=<timestamp>`) in Early
  Hints are fetched speculatively then discarded — pure waste.
- **Ignoring Vary headers**: If your CSS varies by `Accept-Encoding` or `Cookie`, the
  speculative fetch may differ from what the final page needs.
- **Duplicating with `<link rel=preload>`**: If the HTML already contains `<link
  rel=preload>`, a matching Early Hint is redundant and slightly wasteful.

---

## Gotchas

- Workers cannot emit a true 103 response via `return new Response(null, { status: 103 })`
  in all runtimes — the CF runtime may coerce it. Use the `cf.earlyHints` extension or
  rely on Cloudflare's automatic Early Hints feature at the zone level.
- The `Link` header value must not exceed 8 KB; browsers and CDNs silently drop oversized
  headers.
- Safari 17.2+ supports Early Hints only over HTTP/2. HTTP/1.1 Safari ignores them.
- Early Hints are not emitted for non-2xx final responses. If your origin returns 302,
  the hints were wasted — gate hint emission on route confidence.

---

## Verification

```bash
# Check for 103 response in curl (verbose)
curl -v --http2 https://your-worker.example.com/ 2>&1 | grep -E '< HTTP|< Link|103'

# Expected:
# < HTTP/2 103
# < link: </fonts/inter-var.woff2>; rel=preload; as=font; crossorigin
# < link: </css/critical.css>; rel=preload; as=style
# < HTTP/2 200
```

In Chrome DevTools > Network tab, look for `(Early Hints)` entries in the initiator
column with a start time before the document response time. Compare LCP before/after
using Web Vitals Chrome extension or `PerformanceObserver` in your RUM pipeline.

```typescript
// RUM snippet to measure Early Hints benefit
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    if (entry.entryType === 'largest-contentful-paint') {
      console.log('LCP:', entry.startTime);
    }
  }
}).observe({ type: 'largest-contentful-paint', buffered: true });
```

---

## Related

- `workers-critical-css-inline-html-rewriter.md`
- `workers-image-lazy-load-intersection.md`
- `workers-cache-api-fine-grained-control.md`
- `speculative-prefetch-kv.md`

---

## Sources

- RFC 8297: An HTTP Status Code for Indicating Hints — https://datatracker.ietf.org/doc/html/rfc8297
- Cloudflare Early Hints documentation — https://developers.cloudflare.com/cache/about/early-hints/
- web.dev Early Hints guide — https://web.dev/articles/early-hints
- Chrome Status: Early Hints — https://chromestatus.com/feature/5740835259260928
