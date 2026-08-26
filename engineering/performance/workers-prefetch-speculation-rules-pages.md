# Workers Prefetch with Speculation Rules API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Users navigating between pages on a Cloudflare Workers-served site experience a visible loading delay on each navigation because the browser does not start fetching the next page until the link is clicked. The Speculation Rules API allows the browser to prefetch or prerender candidate pages in the background while the user is still on the current page, making navigations feel near-instant. A Workers middleware layer can inject the rules document dynamically without modifying application code, and Analytics Engine records the impact on navigation timing.

---

## Context
The Speculation Rules API is a JSON document embedded in a `<script type="speculationrules">` tag that tells supporting browsers (Chrome 109+, Edge 109+) which URLs to prefetch or prerender. Prefetch downloads the response and stores it in the prefetch cache; prerender goes further and executes JavaScript and applies CSS in a background tab that is swapped in on navigation. Workers middleware intercepts every HTML response, reads or constructs the speculation rules document from KV (to avoid recomputing it per-request), and injects the script tag before `</body>`. Mobile devices are excluded from prerendering because network and battery constraints make it counterproductive — the Worker inspects the `Save-Data` and `ECT` headers or the `viewport` size hint derived from a cookie set on first visit. Navigation timing (TTFB of the navigated page, LCP delta) is recorded to Analytics Engine via a small inline script that runs `performance.getEntriesByType('navigation')` on `DOMContentLoaded`.

---

## Section 1 — Wrangler Config

```toml
# wrangler.toml
name = "speculation-rules-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[kv_namespaces]]
binding = "RULES_KV"
id = "<your-kv-namespace-id>"

[[analytics_engine_datasets]]
binding = "AE"
dataset = "navigation_timing"
```

## Section 2 — Implementation

```typescript
// src/index.ts
import type { KVNamespace, AnalyticsEngineDataset } from '@cloudflare/workers-types';

export interface Env {
  RULES_KV: KVNamespace;
  AE: AnalyticsEngineDataset;
}

/** KV key under which the serialised speculation rules are stored. */
const RULES_KV_KEY = 'speculation-rules:v1';
/** How long to cache the rules document in the Worker's memory per request. */
const RULES_TTL_MS = 60_000;

/** Default speculation rules — injected into every HTML page. */
const DEFAULT_RULES = {
  prefetch: [
    {
      source: 'document',
      where: {
        and: [
          { href_matches: '/*' },
          { not: { href_matches: '/admin/*' } },
          { not: { href_matches: '/api/*' } },
        ],
      },
      eagerness: 'moderate',
    },
  ],
  prerender: [
    {
      source: 'document',
      where: { href_matches: '/articles/*' },
      eagerness: 'conservative',
    },
  ],
};

/** In-process cache so we don't hit KV on every request. */
let rulesCache: { json: string; expiresAt: number } | null = null;

async function getSpeculationRules(kv: KVNamespace): Promise<string> {
  const now = Date.now();
  if (rulesCache && now < rulesCache.expiresAt) return rulesCache.json;

  const stored = await kv.get(RULES_KV_KEY);
  const json = stored ?? JSON.stringify(DEFAULT_RULES);
  rulesCache = { json, expiresAt: now + RULES_TTL_MS };
  return json;
}

/**
 * Determine whether this request comes from a mobile / low-end device.
 * We skip prerendering on mobile to preserve battery and data.
 */
function isMobileOrConstrained(request: Request): boolean {
  const saveData  = request.headers.get('Save-Data');
  const ect       = request.headers.get('ECT');         // Effective Connection Type
  const ua        = request.headers.get('User-Agent') ?? '';
  const viewport  = request.headers.get('Cookie')
    ?.split(';')
    .find((c) => c.trim().startsWith('vw='))
    ?.split('=')?.[1];

  if (saveData === 'on') return true;
  if (ect === '2g' || ect === 'slow-2g') return true;
  if (/Mobile|Android/i.test(ua)) return true;
  if (viewport && Number(viewport) < 768) return true;
  return false;
}

/** Inline analytics script — records navigation timing to Analytics Engine. */
const ANALYTICS_SCRIPT = `
<script>
(function(){
  function record(){
    try{
      var e=performance.getEntriesByType('navigation')[0];
      if(!e)return;
      fetch('/__ae/nav',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          ttfb:Math.round(e.responseStart),
          domContentLoaded:Math.round(e.domContentLoadedEventEnd),
          load:Math.round(e.loadEventEnd),
          activationType:e.activationStart>0?'prerender':'navigate',
          url:location.pathname
        }),
        keepalive:true
      });
    }catch(ex){}
  }
  if(document.readyState==='complete')record();
  else window.addEventListener('load',record);
})();
<\/script>`;

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // ── Handle analytics beacon from the inline script ───────────────────
    if (request.method === 'POST' && url.pathname === '/__ae/nav') {
      try {
        const data = await request.json<{
          ttfb: number;
          domContentLoaded: number;
          load: number;
          activationType: string;
          url: string;
        }>();
        env.AE.writeDataPoint({
          blobs:   [data.url, data.activationType],
          doubles: [data.ttfb, data.domContentLoaded, data.load],
          indexes: [data.activationType],
        });
      } catch {}
      return new Response(null, { status: 204 });
    }

    // ── Admin endpoint: update speculation rules stored in KV ────────────
    if (request.method === 'PUT' && url.pathname === '/__admin/speculation-rules') {
      const body = await request.json<unknown>();
      await env.RULES_KV.put(RULES_KV_KEY, JSON.stringify(body));
      rulesCache = null; // invalidate in-process cache
      return new Response('Updated', { status: 200 });
    }

    // ── Proxy the request upstream (or serve from your app) ─────────────
    // In a real deployment, replace this with your actual fetch-to-origin.
    const upstreamResponse = await fetch(request);

    // Only inject into HTML responses
    const contentType = upstreamResponse.headers.get('Content-Type') ?? '';
    if (!contentType.includes('text/html')) return upstreamResponse;

    const mobile = isMobileOrConstrained(request);
    const rulesJson = await getSpeculationRules(env.RULES_KV);

    // On mobile, strip prerender rules to reduce data usage
    let rules = rulesJson;
    if (mobile) {
      try {
        const parsed = JSON.parse(rulesJson) as typeof DEFAULT_RULES;
        const mobileRules = { ...parsed, prerender: [] };
        rules = JSON.stringify(mobileRules);
      } catch {
        rules = rulesJson;
      }
    }

    // Use a TransformStream to inject the tags before </body>
    const { readable, writable } = new TransformStream();
    const writer = writable.getWriter();
    const enc = new TextEncoder();
    const dec = new TextDecoder();

    // Collect the body and inject before </body>
    // Note: for very large pages prefer a streaming injection approach.
    const original = await upstreamResponse.text();
    const INJECTION = `
<script type="speculationrules">${rules}<\/script>
${ANALYTICS_SCRIPT}
`;
    const injected = original.includes('</body>')
      ? original.replace('</body>', `${INJECTION}</body>`)
      : original + INJECTION;

    // Fire-and-forget the write so the Response can be returned immediately
    (async () => {
      await writer.write(enc.encode(injected));
      await writer.close();
    })();

    const headers = new Headers(upstreamResponse.headers);
    // Allow the browser to interpret the updated content length
    headers.delete('Content-Length');
    headers.set('Vary', 'Save-Data, ECT, User-Agent');

    return new Response(readable, {
      status: upstreamResponse.status,
      headers,
    });
  },
};
```

## Section 3 — Benchmark / Verification

```typescript
// scripts/verify-speculation-rules.ts
// Fetches a page and confirms the speculation rules script is present.
import { JSDOM } from 'jsdom';

const BASE = process.env.TARGET_URL ?? 'http://localhost:8787/';

(async () => {
  const res = await fetch(BASE, {
    headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125' },
  });
  const html = await res.text();
  const dom = new JSDOM(html);
  const scripts = [...dom.window.document.querySelectorAll('script[type="speculationrules"]')];

  if (scripts.length === 0) {
    console.error('FAIL: No speculation rules script found');
    process.exit(1);
  }

  const parsed = JSON.parse(scripts[0].textContent ?? '{}');
  console.log('OK: speculation rules injected');
  console.log('  prefetch rules:', parsed.prefetch?.length ?? 0);
  console.log('  prerender rules:', parsed.prerender?.length ?? 0);

  // Verify mobile stripping
  const mobileRes = await fetch(BASE, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit Mobile Safari',
    },
  });
  const mobileDom = new JSDOM(await mobileRes.text());
  const mobileScript = mobileDom.window.document.querySelector('script[type="speculationrules"]');
  const mobileParsed = JSON.parse(mobileScript?.textContent ?? '{}');
  const prerenderCount = mobileParsed.prerender?.length ?? 0;
  console.log(`Mobile prerender rules: ${prerenderCount} (expected 0)`);
  if (prerenderCount !== 0) {
    console.error('FAIL: prerender rules not stripped on mobile');
    process.exit(1);
  }
  console.log('All checks passed.');
})();
```

---

## Anti-patterns
- **Injecting prerender rules for authenticated pages** — Prerendering pages with session-dependent content can cause one user's page to be served to another if caching is misconfigured; restrict prerender rules to public, unauthenticated URLs.
- **Using `eagerness: "eager"`** — This prerenders all matching links immediately, consuming significant bandwidth and CPU; start with `'conservative'` (on hover with pointer, on touch-start) and promote to `'moderate'` after measuring impact.
- **Skipping the `Vary` header** — Without `Vary: Save-Data, ECT, User-Agent`, a CDN may serve the mobile (no-prerender) response to desktop users; always set `Vary` when the response differs by device.
- **Not expiring the KV rules cache** — Stale rules remain in Worker memory for up to `RULES_TTL_MS`; keep the TTL short (≤60 s) for rules you need to update frequently.

---

## Gotchas
- Speculation Rules are supported in Chrome/Edge 109+ and Samsung Internet 23+; Firefox and Safari ignore the tag silently, so there is no downside to injecting it universally.
- Prerendered pages count as page views in some analytics platforms; ensure your analytics script checks `performance.getEntriesByType('navigation')[0].activationStart > 0` and deduplicates prerender activations.
- Workers `fetch(request)` passes the original client request upstream including cookies; ensure the origin does not return `Set-Cookie` headers that would be cached alongside the speculation rules injection.
- Analytics Engine `writeDataPoint` is fire-and-forget; the runtime does not guarantee delivery if the isolate is evicted immediately after the write — use `waitUntil` in a `FetchEvent` context for guaranteed delivery.

---

## Verification

```bash
# Install jsdom for the verification script
npm install --save-dev jsdom @types/jsdom

# Start dev server
npx wrangler dev --local

# Run verification script
TARGET_URL=http://localhost:8787/ npx tsx scripts/verify-speculation-rules.ts

# Check Analytics Engine data (after deploying to production)
npx wrangler analytics-engine query \
  --dataset navigation_timing \
  --query "SELECT blob2 AS activation_type, AVG(double1) AS avg_ttfb_ms, COUNT() AS hits \
           FROM navigation_timing \
           GROUP BY blob2 ORDER BY hits DESC"
```

---

## Related
- `workers-response-streaming-ttfb-optimization.md`
- `d1-read-replica-routing-workers.md`

---

## Sources
- Speculation Rules API — https://developer.chrome.com/docs/web-platform/prerender-pages
- Cloudflare Workers Analytics Engine — https://developers.cloudflare.com/analytics/analytics-engine/
- W3C Speculation Rules Spec — https://wicg.github.io/nav-speculation/speculation-rules.html
