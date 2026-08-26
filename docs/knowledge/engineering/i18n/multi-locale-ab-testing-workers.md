# Multi-Locale A/B Testing at the Cloudflare Edge

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Product and growth teams want to run A/B experiments where each variant carries different copy,
layouts, or locale-specific UI patterns — but a monolithic origin server serialises locale detection
and experiment assignment into a slow, inconsistent path.

## Context
Cloudflare Workers can resolve both locale and experiment bucket in a single edge hop before the
origin is contacted, eliminating a round-trip and ensuring consistent assignment across page
navigations. Experiment configuration is stored in a KV namespace so variants can be updated without
a code deploy. Assignment is deterministic per visitor (using a hashed visitor ID + experiment key)
so the same user always sees the same variant across sessions.

## Locale Detection at the Edge

Resolve locale from, in priority order: a `locale` cookie, the `cf-ipcountry` header mapped to a
default locale, and the `Accept-Language` header. Normalise to BCP 47 before passing to the
experiment engine.

```typescript
// locale.ts
export function detectLocale(request: Request): string {
  const cookie = parseCookie(request.headers.get("cookie") ?? "");
  if (cookie.locale) return cookie.locale;

  const country = request.headers.get("cf-ipcountry") ?? "";
  const countryDefault: Record<string, string> = {
    DE: "de-DE", FR: "fr-FR", JP: "ja-JP", SA: "ar-SA", BR: "pt-BR",
  };
  if (countryDefault[country]) return countryDefault[country];

  const accept = request.headers.get("accept-language") ?? "en";
  return accept.split(",")[0].trim().split(";")[0];
}

function parseCookie(header: string): Record<string, string> {
  return Object.fromEntries(
    header.split(";").map(p => p.trim().split("=").map(decodeURIComponent))
  );
}
```

## Experiment Assignment: Deterministic Bucketing

Hash the visitor ID (from a first-party cookie or Cloudflare's bot management score header) together
with the experiment key. Take the result modulo 100 to produce a stable 0–99 bucket.

```typescript
// bucketing.ts
async function assignBucket(visitorId: string, experimentKey: string): Promise<number> {
  const input = `${experimentKey}:${visitorId}`;
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
  const view = new DataView(buf);
  // Use the first 4 bytes as a uint32 for uniform distribution
  return view.getUint32(0) % 100;
}

export async function resolveVariant(
  visitorId: string,
  experiment: ExperimentConfig
): Promise<string> {
  const bucket = await assignBucket(visitorId, experiment.key);
  let cumulative = 0;
  for (const [variantId, weight] of Object.entries(experiment.weights)) {
    cumulative += weight;
    if (bucket < cumulative) return variantId;
  }
  return experiment.control;
}
```

## Experiment Configuration in KV

Store experiment definitions as JSON in Workers KV. Use a short TTL (60 s) to allow fast rollouts
without requiring a Worker redeploy.

```typescript
// experiment.ts
export interface ExperimentConfig {
  key: string;
  control: string;
  weights: Record<string, number>; // variant -> % allocation, must sum to 100
  locales?: string[];              // null = all locales; array = restricted locales
  enabled: boolean;
}

export async function loadExperiment(
  kv: KVNamespace,
  experimentKey: string
): Promise<ExperimentConfig | null> {
  return kv.get<ExperimentConfig>(`experiment:${experimentKey}`, {
    type: "json",
    cacheTtl: 60,
  });
}
```

## Locale-Gated Variant Delivery

Combine locale and variant to serve different content. The Worker rewrites a query parameter that
the origin server reads, avoiding the need to teach the origin about experiment infrastructure.

```typescript
// worker.ts
import { detectLocale } from "./locale";
import { loadExperiment, ExperimentConfig } from "./experiment";
import { resolveVariant } from "./bucketing";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const locale = detectLocale(request);
    const visitorId = getOrCreateVisitorId(request);
    const experiment = await loadExperiment(env.EXPERIMENTS_KV, "homepage_hero_2026q3");

    let variant = "control";
    if (experiment?.enabled && (!experiment.locales || experiment.locales.includes(locale))) {
      variant = await resolveVariant(visitorId, experiment);
    }

    const url = new URL(request.url);
    url.searchParams.set("ab_variant", variant);
    url.searchParams.set("locale", locale);

    const originRequest = new Request(url.toString(), request);
    const response = await fetch(originRequest);

    // Persist the visitor ID in a first-party cookie for cross-request consistency
    const headers = new Headers(response.headers);
    headers.append("Set-Cookie", `vid=${visitorId}; Path=/; SameSite=Lax; Max-Age=31536000`);
    headers.append("Vary", "Cookie, Accept-Language");

    ctx.waitUntil(recordAssignment(env.ANALYTICS, locale, variant, visitorId));
    return new Response(response.body, { status: response.status, headers });
  },
};

function getOrCreateVisitorId(request: Request): string {
  const match = request.headers.get("cookie")?.match(/vid=([^;]+)/);
  return match ? match[1] : crypto.randomUUID();
}
```

## Locale-Aware Analytics Reporting

Emit a structured event to an Analytics Engine dataset so results can be sliced by locale and
variant. Use `writeDataPoint` with indexed blobs for locale and variant.

```typescript
// analytics.ts
async function recordAssignment(
  ae: AnalyticsEngineDataset,
  locale: string,
  variant: string,
  visitorId: string
): Promise<void> {
  ae.writeDataPoint({
    blobs: [locale, variant, visitorId],
    indexes: [`${locale}::${variant}`],
    doubles: [1],
  });
}
```

Query in Cloudflare Analytics Engine SQL:
```sql
SELECT
  blob1 AS locale,
  blob2 AS variant,
  SUM(double1) AS assignments
FROM experiment_assignments
WHERE timestamp > NOW() - INTERVAL '7' DAY
GROUP BY locale, variant
ORDER BY locale, variant;
```

## Anti-patterns
- Using IP address alone for locale detection — VPN and CDN egress nodes produce wrong countries
- Assigning variant client-side after page load — causes layout flash and corrupts analytics
- Running the same experiment key across incompatible locale groups — compare only within locale
- Storing experiment state in `globalThis` without a TTL — stale configs persist for isolate lifetime
- Returning different HTML for the same URL without a `Vary: Cookie` header — CDN caches collapse

## Gotchas
- `cf-ipcountry` is always uppercase ISO 3166-1 alpha-2; `T1` means Tor network — map it to a safe default
- Cloudflare KV `cacheTtl` is the edge cache TTL, not the in-isolate memory TTL; set both intentionally
- BCP 47 tags from `Accept-Language` may include script subtags (`zh-Hant`); normalise before lookup
- A/B tests in RTL locales (Arabic, Hebrew) need RTL-safe variant copy — not just translated control copy
- Worker CPU time limits (50 ms on free, 30 s on paid) apply to the entire fetch including crypto.subtle calls

## Verification
1. Curl the Worker 1000 times with the same `Cookie: vid=<uuid>` — assert exactly one variant is
   returned every time (deterministic assignment).
2. Send requests with `Accept-Language: de` and `cf-ipcountry: FR` — assert `fr-FR` wins (country
   takes priority over header).
3. Set `enabled: false` on the KV experiment config and confirm all requests receive `variant=control`.
4. Query Analytics Engine after 500 test requests and confirm per-locale bucket distribution is
   within ±3% of the configured weights.

## Related
- `/documentation/docs/policies/i18n/cloudflare-workers-geolocation-locale-routing.md`
- `/documentation/docs/policies/i18n/locale-detection-browser.md`
- `/documentation/docs/policies/i18n/language-detection-workers-accept-language.md`
- `/documentation/docs/policies/i18n/content-negotiation-vary-header.md`
- `/documentation/docs/policies/i18n/locale-persistence-cookies-storage-2026.md`

## Sources
- Cloudflare Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
- Web Crypto `crypto.subtle.digest`: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
- BCP 47 language tags: https://www.rfc-editor.org/rfc/rfc5646
