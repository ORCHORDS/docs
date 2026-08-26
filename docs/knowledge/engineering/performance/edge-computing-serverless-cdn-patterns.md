# Edge Computing — Serverless Edge Functions, CDN Workers, and Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your API servers are deployed in a single region (e.g., us-east-1), and
users in Europe, Asia, and Australia experience 200-400ms latency on
every request. You cache static assets on a CDN, but dynamic content
(API responses, personalized pages, authentication checks) always hits
the origin server. You want to run compute logic closer to users without
managing servers in multiple regions.

## Context

Edge computing runs application code at CDN points of presence (PoPs)
distributed globally — typically 200-300+ locations. In 2026, edge
functions deliver sub-5ms cold starts (vs. 200-500ms for traditional
serverless), run in lightweight V8 isolates or WebAssembly sandboxes,
and cost up to 70% less than regional serverless for suitable workloads.
The major platforms are Cloudflare Workers (300+ PoPs), Vercel Edge
Functions (built on Cloudflare), Deno Deploy (35+ regions), and AWS
Lambda@Edge / CloudFront Functions. The pattern that works in 2026:
edge for latency-sensitive, stateless logic; origin for complex,
stateful business logic.

## Edge vs. origin decision

```
Run at the edge:
  → Authentication / JWT validation
  → A/B testing and feature flags
  → Geolocation-based routing
  → Request/response transformation
  → API rate limiting
  → Bot detection and WAF rules
  → Static page rendering (SSR)
  → Image optimization and resizing
  → URL redirects and rewrites
  → Cache key computation

Run at the origin:
  → Database transactions (writes)
  → Complex business logic
  → Long-running processes (>30s)
  → Operations requiring large memory (>128MB)
  → Stateful workflows
  → Background job processing
```

## Platform comparison

| Feature | Cloudflare Workers | Vercel Edge | Lambda@Edge | Deno Deploy |
|---|---|---|---|---|
| Runtime | V8 isolates | V8 (Cloudflare) | Node.js container | V8 isolates |
| Cold start | <5ms | <5ms | 200-500ms | <10ms |
| CPU limit | 10-30ms (free), 30s (paid) | 25s | 30s | 50ms-10min |
| Memory | 128MB | 128MB | 128-10240MB | 512MB |
| Locations | 300+ | 300+ (Cloudflare) | 200+ (CloudFront) | 35+ |
| Pricing | Per request + CPU time | Per request | Per request + GB-s | Per request + CPU time |
| State | KV, D1, Durable Objects | KV, Postgres (Neon) | DynamoDB, S3 | KV, Queues |
| Wasm support | Yes | Limited | No | Yes |

## Patterns

### Authentication at the edge

```javascript
export default {
  async fetch(request) {
    const token = request.headers.get('Authorization')?.replace('Bearer ', '');
    if (!token) {
      return new Response('Unauthorized', { status: 401 });
    }

    const isValid = await verifyJWT(token, JWT_SECRET);
    if (!isValid) {
      return new Response('Invalid token', { status: 403 });
    }

    const response = await fetch(request);
    return response;
  }
};

async function verifyJWT(token, secret) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw', encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false, ['verify']
  );
  const [header, payload, signature] = token.split('.');
  const data = encoder.encode(`${header}.${payload}`);
  const sig = Uint8Array.from(atob(signature.replace(/-/g,'+').replace(/_/g,'/')),
    c => c.charCodeAt(0));
  return crypto.subtle.verify('HMAC', key, sig, data);
}
```

### Geolocation routing

```javascript
export default {
  async fetch(request) {
    const country = request.headers.get('CF-IPCountry') || 'US';
    const origins = {
      US: 'https://api-us.example.com',
      DE: 'https://api-eu.example.com',
      JP: 'https://api-apac.example.com',
    };
    const region = country in origins ? country :
      ['GB','FR','IT','ES','NL'].includes(country) ? 'DE' :
      ['JP','KR','AU','SG','IN'].includes(country) ? 'JP' : 'US';

    const url = new URL(request.url);
    url.hostname = new URL(origins[region]).hostname;
    return fetch(new Request(url, request));
  }
};
```

### A/B testing at the edge

```javascript
export default {
  async fetch(request) {
    const url = new URL(request.url);
    let variant = getCookie(request, 'ab-variant');

    if (!variant) {
      variant = Math.random() < 0.5 ? 'control' : 'treatment';
    }

    const response = await fetch(request);
    const newResponse = new Response(response.body, response);

    newResponse.headers.set('X-Variant', variant);
    newResponse.headers.set(
      'Set-Cookie',
      `ab-variant=${variant}; Path=/; Max-Age=86400; SameSite=Lax`
    );

    if (variant === 'treatment') {
      return new HTMLRewriter()
        .on('#hero-cta', { element(el) { el.setAttribute('class', 'cta-v2'); } })
        .transform(newResponse);
    }
    return newResponse;
  }
};
```

### Smart caching with stale-while-revalidate

```javascript
export default {
  async fetch(request, env) {
    const cacheKey = new Request(request.url, request);
    const cache = caches.default;

    let response = await cache.match(cacheKey);
    if (response) {
      if (isStale(response)) {
        event.waitUntil(revalidate(cacheKey, cache, env));
      }
      return response;
    }

    response = await fetch(request);
    response = new Response(response.body, response);
    response.headers.set('Cache-Control', 'public, max-age=60, stale-while-revalidate=300');
    event.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  }
};
```

## Anti-patterns

- **Database queries at the edge** — connecting to a centralized
  database from 300 edge locations creates connection storms and adds
  latency from edge-to-origin round trips. Use edge-native storage
  (KV, D1) for reads, and proxy writes to the origin.
- **Large bundles at the edge** — deploying 10MB+ bundles to edge
  functions. Edge runtimes have memory limits (128MB) and cold start
  increases with bundle size. Keep edge functions small and focused.
- **Stateful logic at the edge** — storing session state in edge
  function memory. Edge functions are ephemeral and run on different
  PoPs across requests. Use external state (KV store, Durable Objects)
  for any state that must persist.
- **Moving everything to the edge** — migrating complex business
  logic that does not benefit from edge proximity. If the function
  needs to call the origin database for every request, running at the
  edge adds a hop instead of removing one.

## Gotchas

- **Node.js compatibility** — edge runtimes use V8 isolates, not
  Node.js. Many npm packages that use `fs`, `net`, `child_process`,
  or other Node.js APIs do not work. Check compatibility before
  deploying.
- **CPU time limits** — edge functions are billed by CPU time, not
  wall-clock time. A function that waits 5 seconds for an origin
  response uses minimal CPU time, but one that runs a tight loop for
  100ms may exceed limits. Offload CPU-intensive work to the origin.
- **Regional data regulations** — running code at the edge means
  processing data in the country where the user is located. GDPR,
  data residency laws, and cross-border data transfer rules may
  require restricting which PoPs handle certain requests.
- **Debugging edge functions** — traditional debuggers do not attach
  to edge runtimes. Use structured logging, Cloudflare Workers Tail,
  and local development simulators (wrangler dev, vercel dev) for
  debugging.

## Verification

- Latency-sensitive operations run at the edge (auth, routing, caching).
- Complex business logic remains at the origin.
- Edge functions are small (<1MB) and stateless.
- Edge-native storage (KV, D1) is used instead of origin database calls.
- Performance is measured by TTFB from multiple global regions.
- Data residency requirements are met with PoP restrictions.

## Related

- `documentation/docs/policies/cloudflare/durable-objects-real-time-state.md`
- `documentation/docs/policies/performance/api-rate-limiting-algorithms.md`
- `documentation/docs/policies/architecture/webassembly-component-model-patterns.md`

## Source URLs (verified 2026-08-16)

- Edge Computing 2026: Cloudflare Workers, Fastly, Lambda@Edge — https://devstarsj.github.io/2026/03/26/edge-computing-cloudflare-workers-guide-2026/
- Edge Computing for Frontend Developers — https://daily.dev/blog/edge-computing-frontend-developers-cloudflare-workers-deno-deploy-vercel/
- Edge Functions and Serverless Computing 2026 — https://zylos.ai/research/2026-01-23-edge-functions-serverless-computing/
- Edge Computing for Web Developers: Cloudflare and Vercel 2026 — https://locallylost.com/guides/edge-computing-for-web-developers-cloudflare-vercel-2026/
