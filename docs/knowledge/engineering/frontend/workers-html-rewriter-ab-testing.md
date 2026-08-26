# A/B Testing with Workers HTMLRewriter

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You want to run A/B tests on your Cloudflare-proxied frontend without modifying origin HTML or deploying JavaScript to the browser. The HTMLRewriter API lets a Worker intercept the response stream and surgically rewrite elements — swapping CTA copy, changing hero image sources — before bytes reach the user, with zero client-side flicker.

---

## Context
Cloudflare Workers sit in front of your origin and can transform responses in flight using the streaming `HTMLRewriter` API. A/B assignment is determined by hashing a stable user identifier (from a cookie) so the same user always lands in the same bucket. The variant is stored in KV for fast lookup and sticky assignment, and exposure events are written to Analytics Engine for downstream analysis. A response header `X-AB-Variant` records the bucket for observability without exposing it to client-side JavaScript.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "orchords-ab"
compatibility_date = "2025-09-01"
main = "src/worker.ts"

[[kv_namespaces]]
binding = "AB_ASSIGNMENTS"
id = "<YOUR_KV_NAMESPACE_ID>"
preview_id = "<YOUR_KV_PREVIEW_ID>"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "ab_exposures"
```

---

## Section 2 — Worker Implementation

```typescript
// src/worker.ts
import { Env, ABVariant, hashToBucket } from './lib';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Only A/B test HTML page requests, not assets
    const isPageRequest =
      request.headers.get('Accept')?.includes('text/html') &&
      !url.pathname.match(/\.(js|css|png|jpg|svg|ico|woff2?)$/);

    if (!isPageRequest) {
      return fetch(request);
    }

    // Resolve or assign variant
    const userId = getUserId(request);
    const variant = await resolveVariant(userId, env);

    // Fetch origin
    const originResponse = await fetch(request);
    if (!originResponse.ok || !originResponse.headers.get('Content-Type')?.includes('text/html')) {
      return originResponse;
    }

    // Log exposure asynchronously
    logExposure(env, userId, variant, url.pathname);

    // Rewrite and return
    const rewritten = rewriteResponse(originResponse, variant);
    rewritten.headers.set('X-AB-Variant', variant);
    rewritten.headers.set('Vary', 'Cookie');
    return rewritten;
  },
};

function getUserId(request: Request): string {
  const cookie = request.headers.get('Cookie') ?? '';
  const match = cookie.match(/(?:^|;\s*)uid=([^;]+)/);
  return match ? match[1] : 'anonymous-' + crypto.randomUUID();
}

async function resolveVariant(
  userId: string,
  env: Env
): Promise<ABVariant> {
  const cacheKey = `variant:${userId}`;
  const cached = await env.AB_ASSIGNMENTS.get(cacheKey);
  if (cached === 'A' || cached === 'B') return cached;

  const bucket = await hashToBucket(userId);
  await env.AB_ASSIGNMENTS.put(cacheKey, bucket, {
    expirationTtl: 60 * 60 * 24 * 30, // 30 days
  });
  return bucket;
}

function rewriteResponse(response: Response, variant: ABVariant): Response {
  const variantConfig = VARIANTS[variant];
  return new HTMLRewriter()
    .on('button[data-cta]', {
      element(el) {
        el.setInnerContent(variantConfig.ctaText);
      },
    })
    .on('img[data-hero]', {
      element(el) {
        el.setAttribute('src', variantConfig.heroSrc);
        el.setAttribute('alt', variantConfig.heroAlt);
      },
    })
    .on('meta[name="ab-variant"]', {
      element(el) {
        el.setAttribute('content', variant);
      },
    })
    .transform(response);
}

function logExposure(
  env: Env,
  userId: string,
  variant: ABVariant,
  path: string
): void {
  // Fire-and-forget; do not await to avoid blocking response
  try {
    env.AE.writeDataPoint({
      blobs: [userId, variant, path],
      doubles: [Date.now()],
      indexes: [variant],
    });
  } catch {
    // Silently swallow Analytics Engine errors
  }
}
```

```typescript
// src/lib.ts
export type ABVariant = 'A' | 'B';

export interface Env {
  AB_ASSIGNMENTS: KVNamespace;
  AE: AnalyticsEngineDataset;
}

export const VARIANTS: Record<ABVariant, { ctaText: string; heroSrc: string; heroAlt: string }> = {
  A: {
    ctaText: 'Start Learning',
    heroSrc: '/images/hero-guitar-a.webp',
    heroAlt: 'Person playing guitar',
  },
  B: {
    ctaText: 'Try It Free',
    heroSrc: '/images/hero-guitar-b.webp',
    heroAlt: 'Close-up of guitar chords',
  },
};

/**
 * Deterministic bucket assignment using SubtleCrypto SHA-256.
 * Returns 'A' for the first 50% of the hash space, 'B' for the rest.
 */
export async function hashToBucket(userId: string): Promise<ABVariant> {
  const encoder = new TextEncoder();
  const data = encoder.encode(`ab-v1:${userId}`);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = new Uint8Array(hashBuffer);
  // Use the first byte: 0-127 → A, 128-255 → B
  return hashArray[0] < 128 ? 'A' : 'B';
}
```

---

## Section 3 — Analytics Query & Testing

```typescript
// Query P-value proxy: exposure counts per variant per page
// Run in Cloudflare Analytics Engine SQL API
const QUERY = `
  SELECT
    blob2 AS variant,
    blob3 AS page_path,
    COUNT()  AS exposures
  FROM ab_exposures
  WHERE timestamp > NOW() - INTERVAL '7' DAY
  GROUP BY variant, page_path
  ORDER BY page_path, variant
`;

// Fetch via REST API
async function queryExposures(accountId: string, apiToken: string) {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'text/plain',
      },
      body: QUERY,
    }
  );
  return res.json();
}
```

```bash
# Local testing with Miniflare
npx wrangler dev --local --port=8787

# Force variant A
curl -H 'Cookie: uid=test-user-a' http://localhost:8787/ | grep 'data-cta'

# Force variant B by using a UID that hashes to B
curl -H 'Cookie: uid=test-user-z999' http://localhost:8787/ | grep 'data-cta'

# Check response header
curl -I -H 'Cookie: uid=test-user-a' http://localhost:8787/ | grep X-AB-Variant

# Deploy
npx wrangler deploy
```

---

## Anti-patterns
- **Assigning variant client-side in JavaScript** — This causes a visible flicker (FOUC) as the page renders before the JS runs; always assign at the edge.
- **Using `Math.random()` for bucket assignment** — Random assignment is not sticky; the same user gets different buckets on each request, corrupting experiment data.
- **Awaiting Analytics Engine writes in the critical path** — `writeDataPoint` should be fire-and-forget; awaiting it adds latency to every page response.
- **Rewriting all responses regardless of Content-Type** — HTMLRewriter on a binary asset response (image, font) will corrupt the file; always check for `text/html`.

---

## Gotchas
- `HTMLRewriter` is streaming — element handlers must be synchronous; you cannot `await` inside an element handler callback.
- KV `get` returns `null` if the key does not exist, not an empty string — always check for `null` before treating the result as a variant string.
- The `Vary: Cookie` header is critical for correct CDN caching; without it, the CDN may serve a cached variant-A response to a variant-B user.
- Analytics Engine `writeDataPoint` has a `blobs` limit of 20 strings and a `doubles` limit of 20 numbers; exceeding either silently drops the data point.

---

## Verification

```bash
# Verify sticky assignment (same UID always gets same variant)
for i in 1 2 3; do
  curl -s -I -H 'Cookie: uid=stable-user-42' http://localhost:8787/ \
    | grep X-AB-Variant
done

# Confirm KV entry was written
npx wrangler kv key get --binding=AB_ASSIGNMENTS 'variant:stable-user-42'

# Confirm no variant header on asset requests
curl -I http://localhost:8787/styles/main.css | grep X-AB-Variant
```

---

## Related
- `workers-web-vitals-beacon-analytics-engine.md`
- `workers-openapi-zod-swagger-ui.md`

---

## Sources
- Cloudflare HTMLRewriter — https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- Cloudflare Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare KV — https://developers.cloudflare.com/kv/
