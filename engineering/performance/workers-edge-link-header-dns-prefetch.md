# Workers Edge Link Header DNS Prefetch Injection
- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Lighthouse and CrUX data show significant DNS lookup time (100–400 ms) for third-party origins
referenced in page HTML—analytics scripts, font providers, API hosts, CDN domains. These lookups
are not resolved until the browser parses the HTML and discovers the resource. Adding
`<link rel="dns-prefetch">` tags in static HTML helps, but the same origin list must be maintained
in two places. A Workers-based approach injects `Link` response headers dynamically, enabling
centralised management and per-request customisation without touching HTML templates.

## Context

The `Link` HTTP response header (RFC 8288) triggers the browser's resource-hint pipeline identically
to `<link>` tags in `<head>`. For DNS prefetch:

```
Link: <https://fonts.googleapis.com>; rel=dns-prefetch
```

Browsers process `Link` headers before HTML parsing begins—potentially resolving DNS while the
HTML body is still streaming. This gives a timing advantage over in-HTML hints.

Cloudflare Workers intercept every response, making them ideal for injecting `Link` headers
centrally. Combined with Early Hints (103), the hints are dispatched before the final response
body is available—pushing resolution even earlier in the waterfall.

**Delivery hierarchy (fastest to slowest DNS resolution):**
1. `103 Early Hints` → browser resolves DNS while origin is generating the page.
2. `Link` header on `200 OK` → browser resolves DNS as headers arrive.
3. `<link rel="dns-prefetch">` in HTML → browser resolves DNS after `<head>` parsing.

Workers can inject at level 1 (103) or level 2 (200 Link header). This article covers both.

## Static Hint Configuration

```typescript
// src/prefetch-config.ts
export interface PrefetchHint {
  origin: string;
  rel: 'dns-prefetch' | 'preconnect';
  crossOrigin?: 'anonymous' | 'use-credentials';
}

// Centralised hint registry — update here, no HTML deploys needed
export const DEFAULT_HINTS: PrefetchHint[] = [
  { origin: 'https://fonts.googleapis.com',   rel: 'preconnect', crossOrigin: 'anonymous' },
  { origin: 'https://fonts.gstatic.com',       rel: 'preconnect', crossOrigin: 'anonymous' },
  { origin: 'https://static.analytics.com',   rel: 'dns-prefetch' },
  { origin: 'https://cdn.example.com',         rel: 'dns-prefetch' },
  { origin: 'https://api.payments.example',   rel: 'dns-prefetch' },
];

export function buildLinkHeader(hints: PrefetchHint[]): string {
  return hints
    .map((h) => {
      let value = `<${h.origin}>; rel=${h.rel}`;
      if (h.crossOrigin) value += `; crossorigin=${h.crossOrigin}`;
      return value;
    })
    .join(', ');
}
```

## Injecting Link Headers on 200 Responses

```typescript
// src/index.ts
import { DEFAULT_HINTS, buildLinkHeader, PrefetchHint } from './prefetch-config';

interface Env {
  HINT_OVERRIDES?: KVNamespace;   // optional per-path overrides from KV
}

function shouldInjectHints(url: URL): boolean {
  // Inject on HTML document requests only; skip API, assets, fonts
  const skipPrefixes = ['/api/', '/assets/', '/_next/static/', '/favicon'];
  return !skipPrefixes.some((p) => url.pathname.startsWith(p));
}

function mergeHints(
  base: PrefetchHint[],
  overrides: PrefetchHint[],
): PrefetchHint[] {
  const seen = new Set(base.map((h) => h.origin));
  const extra = overrides.filter((h) => !seen.has(h.origin));
  return [...base, ...extra];
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Pass through non-document requests unchanged
    if (!shouldInjectHints(url)) {
      return fetch(request);
    }

    // Fetch per-path hint overrides from KV (optional)
    let hints = DEFAULT_HINTS;
    if (env.HINT_OVERRIDES) {
      const overrideJson = await env.HINT_OVERRIDES.get(url.pathname, 'json') as PrefetchHint[] | null;
      if (overrideJson) {
        hints = mergeHints(DEFAULT_HINTS, overrideJson);
      }
    }

    // Fetch origin response
    const originResponse = await fetch(request);

    // Only inject on HTML responses
    const contentType = originResponse.headers.get('Content-Type') ?? '';
    if (!contentType.includes('text/html')) {
      return originResponse;
    }

    const newHeaders = new Headers(originResponse.headers);
    const existingLink = newHeaders.get('Link');
    const newLink = buildLinkHeader(hints);

    // Append to existing Link header if present (avoid overwriting preload hints from origin)
    newHeaders.set('Link', existingLink ? `${existingLink}, ${newLink}` : newLink);

    return new Response(originResponse.body, {
      status: originResponse.status,
      headers: newHeaders,
    });
  },
} satisfies ExportedHandler<Env>;
```

## 103 Early Hints Integration

```typescript
// src/early-hints.ts
// Note: 103 Early Hints is supported on Cloudflare Pages + Workers (2025+).
// For pure Workers without Pages, 103 is dispatched via the cf object.

export function buildEarlyHintsHeaders(hints: PrefetchHint[]): Headers {
  const headers = new Headers();
  for (const hint of hints) {
    let value = `<${hint.origin}>; rel=${hint.rel}`;
    if (hint.crossOrigin) value += `; crossorigin=${hint.crossOrigin}`;
    headers.append('Link', value);
  }
  return headers;
}

// Usage in a Cloudflare Pages Function:
// export async function onRequest(context: EventContext<Env, string, Data>): Promise<Response> {
//   // Send 103 immediately
//   const earlyHints = buildEarlyHintsHeaders(DEFAULT_HINTS);
//   // context.next() returns 200 after 103 is dispatched by the platform
//   const response = await context.next();
//   // Add Link header to 200 as well for browsers that missed 103
//   const headers = new Headers(response.headers);
//   headers.set('Link', buildLinkHeader(DEFAULT_HINTS));
//   return new Response(response.body, { ...response, headers });
// }
```

## Per-Route Hint Overrides via KV

Store route-specific additional hints in KV for marketing pages with unique third-party integrations:

```typescript
// Populate KV via wrangler or an admin Worker:
// wrangler kv:key put --binding HINT_OVERRIDES "/checkout" \
//   '[{"origin":"https://js.stripe.com","rel":"preconnect","crossOrigin":"anonymous"}]'
```

```typescript
// Admin endpoint to update hints at runtime
async function updateHints(
  kv: KVNamespace,
  path: string,
  hints: PrefetchHint[],
): Promise<void> {
  await kv.put(path, JSON.stringify(hints), { expirationTtl: 86400 });
}
```

## Measuring Impact

```typescript
// src/hint-analytics.ts
// Use Resource Timing API on the client to confirm DNS resolution time
const observer = new PerformanceObserver((list) => {
  for (const entry of list.getEntriesByType('resource') as PerformanceResourceTiming[]) {
    const dnsTime = entry.domainLookupEnd - entry.domainLookupStart;
    if (dnsTime > 0) {
      // DNS was NOT prefetched for this origin — report to RUM
      navigator.sendBeacon('/rum/dns-miss', JSON.stringify({
        origin: new URL(entry.name).origin,
        dnsMs: dnsTime,
      }));
    }
  }
});
observer.observe({ type: 'resource', buffered: true });
```

A successful prefetch shows `domainLookupStart === domainLookupEnd` (0 ms DNS time) for the
hinted origins.

## Anti-patterns

- **Injecting `preconnect` for every third-party origin**: `preconnect` opens a TCP+TLS connection.
  More than 6 preconnects compete for socket budget and can slow the critical path. Use
  `dns-prefetch` for low-priority origins and `preconnect` only for critical ones (fonts, auth).
- **Adding `Link` headers to image, CSS, or JS sub-resources**: the browser ignores resource hints
  on sub-resource responses; only document (HTML) responses benefit.
- **Duplicating origins already in `<link>` tags**: double hints are harmless but waste header
  bytes. If origin HTML already contains hints, skip them in the Worker.
- **Using `crossorigin` on `dns-prefetch`**: `crossorigin` is only meaningful on `preconnect`.
  Adding it to `dns-prefetch` has no effect and inflates the header.
- **Not checking `Content-Type` before injecting**: injecting `Link` headers into JSON API
  responses wastes processing and may confuse HTTP clients.

## Gotchas

- The `Link` header value is comma-separated; each directive is `<url>; rel=...`. Concatenating
  multiple hints as separate `Link` header lines works in most browsers but is non-standard—prefer
  comma-joining into a single header.
- Cloudflare strips or rewrites some response headers. Verify `Link` headers pass through with
  `curl -si https://your.domain/ | grep -i '^link:'`.
- `preconnect` without `crossorigin` opens an anonymous connection. Fonts require
  `crossorigin=anonymous` to reuse the connection for CORS fetches.
- KV reads add ~2–10 ms to TTFB on the per-path override lookup. Cache the result in a Worker
  isolate-level `Map` with a short TTL to avoid KV reads on every request.
- 103 Early Hints are dispatched before authentication/authorisation logic runs. Do not include
  hints for origins that depend on the authenticated user's plan or region.

## Verification

```bash
# Confirm Link header is present
curl -si https://example.com/ | grep -i '^link:'
# Expected: Link: <https://fonts.googleapis.com>; rel=preconnect; crossorigin=anonymous, ...

# Check Chrome DevTools → Network → document request → Response Headers → Link
# Then Resources → fonts.googleapis.com → Timing → DNS Lookup should be ~0 ms
```

```bash
# Lighthouse CLI — check for "Preconnect to required origins" audit pass
npx lighthouse https://example.com --only-audits=uses-rel-preconnect --output=json \
  | jq '.audits["uses-rel-preconnect"].score'
# Expected: 1 (pass)
```

## Related

- `early-hints-103.md`
- `early-hints-103-cloudflare-pages-mobile.md`
- `dns-prefetch.md`
- `resource-hints-preconnect.md`
- `workers-middleware-chain-performance.md`

## Sources

- RFC 8288 — Web Linking (Link header)
- Cloudflare Docs: Early Hints — https://developers.cloudflare.com/cache/advanced-configuration/early-hints/
- MDN: `rel=dns-prefetch` — https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/rel/dns-prefetch
- MDN: `rel=preconnect` — https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/rel/preconnect
- web.dev: Establish network connections early — https://web.dev/articles/preconnect-and-dns-prefetch
