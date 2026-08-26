# Zero-Overhead A/B Testing at the Cloudflare Edge

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Third-party A/B testing scripts (Optimizely, VWO, Google Optimize) add 100–400 ms of render-blocking overhead and frequently cause cumulative layout shift. Teams want to split traffic between variants without touching client-side JavaScript or sacrificing Core Web Vitals scores.

## Context

Cloudflare Workers intercept every request before it reaches the origin, making them ideal for traffic splitting logic. Variant assignment happens at the edge — zero extra round-trips, zero client-side script weight, no flicker. Sticky sessions are maintained through a lightweight cookie so users stay on the same variant across page loads. Variant performance data is written to Analytics Engine for per-variant Core Web Vitals analysis without a third-party analytics dependency.

## Variant Assignment and Sticky Sessions

The Worker reads an existing assignment cookie; if absent it hashes a random UUID, maps it to a bucket, and sets a `Max-Age` cookie on the response. All subsequent requests from the same browser carry the cookie, producing deterministic variant routing with no server-side state.

```typescript
export interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

const VARIANTS = ['control', 'treatment'] as const;
type Variant = typeof VARIANTS[number];

function assignVariant(seed: string): Variant {
  // Simple 32-bit FNV-1a hash for deterministic bucketing
  let hash = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i);
    hash = (hash * 16777619) >>> 0;
  }
  return VARIANTS[hash % VARIANTS.length];
}

function getOrAssignVariant(request: Request): { variant: Variant; isNew: boolean } {
  const cookie = request.headers.get('Cookie') ?? '';
  const match = cookie.match(/ab_variant=([^;]+)/);
  if (match && (VARIANTS as readonly string[]).includes(match[1])) {
    return { variant: match[1] as Variant, isNew: false };
  }
  const seed = crypto.randomUUID();
  return { variant: assignVariant(seed), isNew: true };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only A/B test GET requests for HTML pages
    if (request.method !== 'GET' || !request.headers.get('Accept')?.includes('text/html')) {
      return fetch(request);
    }

    const { variant, isNew } = getOrAssignVariant(request);

    // Rewrite origin URL to variant-specific path or add header for origin to act on
    const originUrl = new URL(request.url);
    originUrl.searchParams.set('__variant', variant);

    const originRequest = new Request(originUrl.toString(), {
      method: request.method,
      headers: new Headers(request.headers),
      cf: (request as any).cf,
    });
    originRequest.headers.set('X-AB-Variant', variant);

    const originResponse = await fetch(originRequest);

    const response = new Response(originResponse.body, originResponse);

    if (isNew) {
      // Sticky session: 30-day cookie, SameSite=Lax so it survives navigation
      response.headers.append(
        'Set-Cookie',
        `ab_variant=${variant}; Max-Age=2592000; Path=/; SameSite=Lax; Secure`,
      );
    }

    // Emit variant assignment event to Analytics Engine
    env.ANALYTICS.writeDataPoint({
      blobs: [variant, url.pathname, request.headers.get('CF-IPCountry') ?? 'XX'],
      doubles: [1],
      indexes: [variant],
    });

    return response;
  },
};
```

## Tracking Core Web Vitals Per Variant

Client-side RUM collects Core Web Vitals using the `web-vitals` library, then POSTs them to a `/rum` endpoint on the same Worker. The Worker reads the variant cookie from the RUM request and writes the metric to Analytics Engine, enabling per-variant LCP/CLS/INP breakdowns.

```typescript
// /rum endpoint handler — add to the fetch handler above
async function handleRum(request: Request, env: Env): Promise<Response> {
  if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

  let body: { name: string; value: number; id: string };
  try {
    body = await request.json();
  } catch {
    return new Response('Bad Request', { status: 400 });
  }

  const cookie = request.headers.get('Cookie') ?? '';
  const variantMatch = cookie.match(/ab_variant=([^;]+)/);
  const variant = variantMatch ? variantMatch[1] : 'unknown';

  env.ANALYTICS.writeDataPoint({
    blobs: [body.name, variant, body.id],
    doubles: [body.value],
    indexes: [body.name],
  });

  return new Response(null, { status: 204 });
}
```

RUM snippet injected into every HTML response (or placed in your layout component):

```typescript
// Minimal RUM snippet — inject via HTMLRewriter or layout template
const RUM_SNIPPET = `
<script type="module">
  import { onLCP, onCLS, onINP } from 'https://unpkg.com/web-vitals@4/dist/web-vitals.attribution.js';
  const send = (m) => navigator.sendBeacon('/rum', JSON.stringify({ name: m.name, value: m.value, id: m.id }));
  onLCP(send); onCLS(send); onINP(send);
</script>`;

// Use HTMLRewriter to inject the snippet before </body>
function injectRum(response: Response): Response {
  return new HTMLRewriter()
    .on('body', {
      element(el) {
        el.onEndTag((tag) => tag.before(RUM_SNIPPET, { html: true }));
      },
    })
    .transform(response);
}
```

## Querying Per-Variant Metrics in Analytics Engine

Analytics Engine SQL API lets you compare variant performance directly:

```sql
-- Average LCP per variant over the last 7 days
SELECT
  blob2 AS variant,
  avg(double1) AS avg_lcp_ms,
  quantileWeighted(0.75)(double1, 1) AS p75_lcp_ms,
  count() AS sample_count
FROM ANALYTICS_DATASET
WHERE blob1 = 'LCP'
  AND timestamp > NOW() - INTERVAL '7' DAY
GROUP BY variant
ORDER BY avg_lcp_ms ASC;
```

Query via the REST API from your CI pipeline to gate promotion decisions:

```bash
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT blob2 AS variant, avg(double1) AS avg_lcp FROM ANALYTICS_DATASET WHERE blob1 = '\''LCP'\'' GROUP BY variant"
  }' | jq '.data'
```

## Anti-patterns

- Setting the variant cookie with `SameSite=None` without HTTPS — the cookie is silently dropped by modern browsers, causing users to be re-assigned on every request.
- Using the client IP as the assignment seed — IP addresses are shared (NAT, corporate proxies) and change (mobile), producing inconsistent assignment and polluted results.
- Running the A/B test on all resource types (images, fonts, API calls) — limit the Worker to `text/html` responses to avoid variant bleed into cache-keyed assets.
- Directing variant traffic to entirely different origin hosts without adjusting `Cache-Control: Vary` — CDN caches can serve the wrong variant to subsequent users.
- Letting the test run for only 24 hours — weekday vs. weekend traffic patterns require at least a full week of data for valid conclusions.

## Gotchas

- Workers do not expose the raw `Set-Cookie` response header via `response.headers.get('Set-Cookie')` in some runtimes — use `response.headers.getAll('Set-Cookie')` (Cloudflare Workers supports this) when inspecting or merging cookies from the origin.
- Analytics Engine `writeDataPoint` is fire-and-forget and will silently drop data points if the dataset binding is misconfigured in `wrangler.toml`; verify with `wrangler tail` before relying on it in production.
- The `__variant` query parameter added to the origin URL must be stripped from any canonical `<link>` tags the origin emits, otherwise search engines may index variant URLs.

## Verification

```bash
# Confirm variant cookie is set on first visit
curl -si https://example.com/ | grep -i 'set-cookie'
# → set-cookie: ab_variant=treatment; Max-Age=2592000; ...

# Confirm sticky routing — same cookie returns same variant header
curl -si -H "Cookie: ab_variant=treatment" https://example.com/ | grep 'x-ab-variant'

# Tail Worker logs to see real-time assignment events
wrangler tail --format=pretty

# Query Analytics Engine for variant distribution (should be ~50/50)
curl -s "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -d '{"query":"SELECT blob1 AS variant, sum(double1) AS visits FROM DATASET GROUP BY variant"}'
```

## Related

- `performance/analytics-engine-rum-web-vitals.md`
- `performance/cloudflare-workers-performance.md`
- `performance/core-web-vitals-overview.md`
- `performance/kv-read-performance.md`

## Sources

- https://developers.cloudflare.com/workers/examples/ab-testing/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- https://web.dev/articles/vitals
