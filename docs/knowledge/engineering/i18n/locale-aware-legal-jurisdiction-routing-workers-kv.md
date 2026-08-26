# Locale-Aware Legal Jurisdiction Routing — Workers + KV

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your app serves a single Privacy Policy and Terms of Service URL globally. A GDPR audit flags
that EU users must see the EU-specific data-processing addendum; Californian users must see
CCPA disclosures; Brazilian users must see LGPD notices. Hardcoding country checks in the
client leaks legal logic and breaks when a user connects through a VPN to a different region.

## Context

Cloudflare Workers expose `request.cf.country` and `request.cf.region` from Cloudflare's
anycast network before the request reaches your origin. KV stores a mapping of
`country → legal jurisdiction slug` so the routing rules can be updated at runtime without
a deploy. Workers rewrite the URL or inject `X-Legal-Jurisdiction` headers so your front-end
components load the correct document variant.

---

## 1 — KV data model: jurisdiction map

```bash
# Bootstrap jurisdiction map via wrangler CLI
wrangler kv key put --binding LEGAL_KV "jurisdiction:DE" "eu-gdpr"
wrangler kv key put --binding LEGAL_KV "jurisdiction:FR" "eu-gdpr"
wrangler kv key put --binding LEGAL_KV "jurisdiction:IT" "eu-gdpr"
# ... repeat for all 27 EU member states
wrangler kv key put --binding LEGAL_KV "jurisdiction:US-CA" "us-ccpa"
wrangler kv key put --binding LEGAL_KV "jurisdiction:BR"    "br-lgpd"
wrangler kv key put --binding LEGAL_KV "jurisdiction:JP"    "jp-appi"
wrangler kv key put --binding LEGAL_KV "jurisdiction:CN"    "cn-pipl"
wrangler kv key put --binding LEGAL_KV "jurisdiction:IN"    "in-pdpb"
wrangler kv key put --binding LEGAL_KV "jurisdiction:__default__" "global"
```

KV value is a jurisdiction slug that maps to a document version:
```bash
wrangler kv key put --binding LEGAL_KV "doc:privacy:eu-gdpr"  '{"url":"/legal/privacy/eu","version":"2026-05-01"}'
wrangler kv key put --binding LEGAL_KV "doc:privacy:us-ccpa"  '{"url":"/legal/privacy/ccpa","version":"2026-01-01"}'
wrangler kv key put --binding LEGAL_KV "doc:privacy:global"   '{"url":"/legal/privacy","version":"2025-12-01"}'
```

---

## 2 — Jurisdiction resolver

```typescript
// src/jurisdiction.ts

interface DocMeta { url: string; version: string }

/**
 * Resolve legal jurisdiction for a request.
 * Priority: country+region (US-CA) → country → default.
 */
export async function resolveJurisdiction(
  kv: KVNamespace,
  country: string | undefined,
  region: string | undefined,
): Promise<string> {
  if (!country) return 'global';

  // US states have their own rules (CCPA, VCDPA, CPA…)
  if (country === 'US' && region) {
    const stateJurisdiction = await kv.get(`jurisdiction:US-${region}`);
    if (stateJurisdiction) return stateJurisdiction;
  }

  const countryJurisdiction = await kv.get(`jurisdiction:${country}`);
  if (countryJurisdiction) return countryJurisdiction;

  return (await kv.get('jurisdiction:__default__')) ?? 'global';
}

export async function resolveDocUrl(
  kv: KVNamespace,
  docType: 'privacy' | 'terms' | 'cookies',
  jurisdiction: string,
): Promise<DocMeta> {
  const raw = await kv.get(`doc:${docType}:${jurisdiction}`);
  if (raw) return JSON.parse(raw) as DocMeta;
  // Fallback to global
  const fallback = await kv.get(`doc:${docType}:global`);
  return fallback ? JSON.parse(fallback) : { url: `/legal/${docType}`, version: 'unknown' };
}
```

---

## 3 — Worker middleware: rewrite legal links

```typescript
// src/index.ts
import { resolveJurisdiction, resolveDocUrl } from './jurisdiction';

interface Env { LEGAL_KV: KVNamespace }

const LEGAL_PATH_RE = /^\/legal\/(privacy|terms|cookies)(\/.*)?$/;

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url     = new URL(req.url);
    const match   = LEGAL_PATH_RE.exec(url.pathname);

    const country = (req as any).cf?.country  as string | undefined;
    const region  = (req as any).cf?.region   as string | undefined;

    // Resolve jurisdiction for every request (cheap KV read, cached by edge)
    const jurisdiction = await resolveJurisdiction(env.LEGAL_KV, country, region);

    if (match) {
      // Rewrite /legal/privacy → jurisdiction-specific URL
      const docType = match[1] as 'privacy' | 'terms' | 'cookies';
      const meta    = await resolveDocUrl(env.LEGAL_KV, docType, jurisdiction);

      // Redirect to the canonical versioned document
      return Response.redirect(new URL(meta.url, url.origin).href, 302);
    }

    // Pass through all other requests with jurisdiction metadata in header
    const res = await fetch(req);
    const mutable = new Response(res.body, res);
    mutable.headers.set('X-Legal-Jurisdiction', jurisdiction);
    mutable.headers.set('X-Legal-Country',      country ?? 'unknown');
    return mutable;
  },
};
```

---

## 4 — Client-side: read the header and show consent UI

```typescript
// Runs in the browser after the Worker adds the header.
// The header is forwarded by the origin server (add Expose-Headers in CORS config).

async function loadConsentConfig(): Promise<string> {
  const res = await fetch('/api/me');
  return res.headers.get('X-Legal-Jurisdiction') ?? 'global';
}

async function mountConsentBanner(jurisdiction: string): Promise<void> {
  // Only show GDPR banner in EU; show CCPA opt-out in California, etc.
  const bannerMap: Record<string, string> = {
    'eu-gdpr': '/components/consent/gdpr-banner.js',
    'us-ccpa': '/components/consent/ccpa-optout.js',
    'br-lgpd': '/components/consent/lgpd-banner.js',
  };
  const src = bannerMap[jurisdiction];
  if (!src) return;  // global: no mandatory banner
  const script = document.createElement('script');
  script.src = src;
  document.head.appendChild(script);
}

loadConsentConfig().then(mountConsentBanner);
```

---

## 5 — KV bulk-update via API (for legal team self-service)

```typescript
// scripts/update-jurisdiction.ts  — run with `npx tsx`
const ACCOUNT_ID  = process.env.CF_ACCOUNT_ID!;
const NAMESPACE_ID = process.env.LEGAL_KV_NAMESPACE_ID!;
const API_TOKEN   = process.env.CF_API_TOKEN!;

async function putJurisdiction(country: string, slug: string): Promise<void> {
  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/storage/kv/namespaces/${NAMESPACE_ID}/values/jurisdiction:${country}`,
    {
      method: 'PUT',
      headers: { Authorization: `Bearer ${API_TOKEN}`, 'Content-Type': 'text/plain' },
      body: slug,
    },
  );
}

// Extend when a new privacy law comes into effect
await putJurisdiction('AU', 'au-privacy-act');
```

---

## Anti-patterns

- **Using `Accept-Language` for jurisdiction** — a German speaker living in Brazil is subject
  to LGPD, not GDPR. Always use IP-derived country (`cf.country`), not language preference.
- **Hardcoding EU country lists in Worker code** — Brexit already required one emergency deploy;
  use KV so the legal team can update the map without engineering involvement.
- **Redirecting to locale URLs based on jurisdiction** — jurisdiction (legal) and locale
  (language/region preference) are orthogonal; keep them in separate KV namespaces.
- **Caching jurisdiction responses without Vary** — a shared cache that ignores `cf.country`
  serves the wrong document to users in different countries.

## Gotchas

- `request.cf.region` is the ISO 3166-2 subdivision code **without** the country prefix in
  some Cloudflare versions (e.g. `"CA"` for California, not `"US-CA"`). Normalise before
  the KV lookup.
- VPN users will be placed in the VPN exit country. This is acceptable for legal purposes
  (the controlling regulation follows your servers' delivery location), but document the
  approach in your legal ops runbook.
- KV reads at the edge are eventually consistent. After updating a jurisdiction entry,
  existing edge caches may serve the old value for up to 60 seconds. For high-stakes changes
  (a new PIPL enforcement date), purge the namespace or use a versioned key suffix.

## Verification

```bash
# Simulate a German request
curl -H "X-Forwarded-Country: DE" https://your-worker.workers.dev/legal/privacy
# Expected: 302 redirect to /legal/privacy/eu

# Simulate a Californian request
curl -H "X-Forwarded-Country: US" -H "X-Forwarded-Region: CA" \
  https://your-worker.workers.dev/legal/privacy
# Expected: 302 redirect to /legal/privacy/ccpa
```

```typescript
// Unit test (Vitest + miniflare)
import { resolveJurisdiction } from './jurisdiction';

const mockKv = { get: async (k: string) => ({ 'jurisdiction:DE': 'eu-gdpr' })[k] ?? null };
const j = await resolveJurisdiction(mockKv as any, 'DE', undefined);
console.assert(j === 'eu-gdpr', 'Germany should resolve to eu-gdpr');
```

## Related

- `cloudflare-workers-geolocation-locale-routing.md`
- `locale-conditional-feature-flags-workers-kv.md`
- `locale-fallback-chain.md`
- `locale-persistence-cookies-storage-2026.md`
- `workers-locale-context-service-bindings.md`

## Sources

- Cloudflare Workers `request.cf` object — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- Cloudflare KV — https://developers.cloudflare.com/kv/
- GDPR recitals (territorial scope) — https://gdpr.eu/article-3-gdpr/
- CCPA text — https://oag.ca.gov/privacy/ccpa
- LGPD (Lei Geral de Proteção de Dados) — https://www.gov.br/cidadania/pt-br/acesso-a-informacao/lgpd
