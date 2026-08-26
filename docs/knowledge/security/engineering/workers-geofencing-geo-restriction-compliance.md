# Geo-Restriction and Geofencing for Compliance in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your anonymous social platform is subject to GDPR data residency requirements, OFAC sanctions
compliance, or local content-law obligations (e.g. NetzDG in Germany, DSA in the EU, or content
restrictions in specific jurisdictions). You need to block, redirect, or conditionally serve requests
based on the client's country or region — at the edge, before any data is processed, with audit
evidence that enforcement is functioning.

---

## Context

Cloudflare Workers receive the client's country code in `request.cf.country` — a two-letter ISO 3166-1
alpha-2 code derived from Cloudflare's IP geolocation database. Unlike client-supplied headers, this
field is injected by Cloudflare's infrastructure and cannot be spoofed by the client.

Geo-restriction at the Worker level is preferable to WAF geo-blocking rules for three reasons:

1. **Audit logging** — the Worker can emit a structured event (to Analytics Engine or R2) when a
   geo-block fires, providing a compliance audit trail.
2. **Conditional behavior** — some jurisdictions require different content, not just a block. Workers
   can branch on country before touching user data.
3. **Precedence** — Worker logic runs before cache serves a cached response, preventing cached
   restricted content from reaching blocked regions.

---

## 1. Country Resolution and Trust

Always read country from `request.cf`, never from `X-Country` or similar client headers. Validate that
`cf` is present (it may be absent in local dev) and fall back safely.

```typescript
// src/geo/resolver.ts

export interface GeoContext {
  country: string;   // ISO 3166-1 alpha-2, e.g. "DE", "US", "XX" for unknown
  region: string;    // Cloudflare region string, e.g. "CA" for California
  asn: number;
  isDatacenter: boolean;
}

export function resolveGeo(request: Request): GeoContext {
  const cf = request.cf as Record<string, unknown> | undefined;

  return {
    country:      (cf?.country as string)       ?? 'XX',
    region:       (cf?.region as string)        ?? '',
    asn:          Number(cf?.asn               ?? 0),
    isDatacenter: Boolean(cf?.isEUCountry      ?? false), // example cf field
  };
}
```

---

## 2. Jurisdiction Policy Tables

Maintain policy tables in code (for hot-path performance) and back them with KV for dynamic overrides.
Code-level policies are the default; KV overrides allow legal team to update without a deployment.

```typescript
// src/geo/policies.ts

/** Countries subject to full content block (e.g. OFAC sanctions list) */
export const SANCTIONED_COUNTRIES = new Set([
  'CU', 'IR', 'KP', 'RU', 'SY',
  // Update per current OFAC Specially Designated Nationals list
]);

/** Countries requiring GDPR-compliant data handling (EEA + UK + CH) */
export const GDPR_COUNTRIES = new Set([
  'AT','BE','BG','CY','CZ','DE','DK','EE','ES','FI','FR','GR','HR',
  'HU','IE','IS','IT','LI','LT','LU','LV','MT','NL','NO','PL','PT',
  'RO','SE','SI','SK','GB','CH',
]);

/** Countries with content moderation law requiring expedited takedowns */
export const NETZG_COUNTRIES = new Set(['DE','AT','CH']);

export type GeoPolicy =
  | { action: 'allow' }
  | { action: 'block'; reason: string; httpStatus: 451 | 403 }
  | { action: 'gdpr_mode' }
  | { action: 'redirect'; url: string };

export function resolvePolicy(country: string): GeoPolicy {
  if (SANCTIONED_COUNTRIES.has(country)) {
    return {
      action: 'block',
      reason: 'Service unavailable in your region due to legal restrictions.',
      httpStatus: 451, // RFC 7725 — Unavailable For Legal Reasons
    };
  }
  if (GDPR_COUNTRIES.has(country)) {
    return { action: 'gdpr_mode' };
  }
  return { action: 'allow' };
}
```

---

## 3. Geo-Block Middleware

Apply the policy early in the middleware chain — before any D1 reads, KV lookups, or authentication.

```typescript
// src/middleware/geo-block.ts
import { resolveGeo } from '../geo/resolver';
import { resolvePolicy } from '../geo/policies';
import { emitGeoBlockEvent } from '../telemetry/emitter';

export async function geoBlockMiddleware(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response | null> {
  const geo = resolveGeo(request);

  // Check KV for dynamic policy overrides (cached for 60 s in a module variable)
  const overrideRaw = await env.GEO_POLICY_OVERRIDES.get(
    `country:${geo.country}`,
    'json'
  );

  const policy =
    (overrideRaw as ReturnType<typeof resolvePolicy> | null) ??
    resolvePolicy(geo.country);

  if (policy.action === 'block') {
    ctx.waitUntil(
      emitGeoBlockEvent(env, request, geo.country, policy.reason)
    );

    return new Response(
      JSON.stringify({
        error: 'legal_restriction',
        message: policy.reason,
      }),
      {
        status: policy.httpStatus,
        headers: {
          'Content-Type': 'application/json',
          'Link': '<https://www.cloudflare.com/legal/country-block>; rel="blocked-by"',
        },
      }
    );
  }

  if (policy.action === 'redirect') {
    return Response.redirect(policy.url, 302);
  }

  // gdpr_mode and allow: continue; attach geo context for downstream use
  return null;
}
```

---

## 4. GDPR Mode: Conditional Data Processing

For GDPR-jurisdiction clients, suppress analytics, skip optional telemetry writes, and ensure data
is processed only in approved regions. Pass a `GdprContext` to downstream handlers.

```typescript
// src/geo/gdpr.ts
import { GDPR_COUNTRIES } from './policies';

export interface GdprContext {
  required: boolean;
  allowAnalytics: boolean;       // false unless user has consented
  dataResidencyRegion: 'EU' | 'ANY';
}

export function buildGdprContext(country: string): GdprContext {
  const required = GDPR_COUNTRIES.has(country);
  return {
    required,
    allowAnalytics: !required, // conservative default; override on consent
    dataResidencyRegion: required ? 'EU' : 'ANY',
  };
}

// In your Worker handler:
export async function handleRequest(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const geo = resolveGeo(request);
  const gdpr = buildGdprContext(geo.country);

  if (gdpr.required && !hasUserConsent(request)) {
    // Return consent gate response before any data processing
    return new Response(
      JSON.stringify({ error: 'consent_required', gdpr: true }),
      { status: 451 }
    );
  }

  // ... downstream handlers receive gdpr context
}

function hasUserConsent(request: Request): boolean {
  // Check consent cookie or header set by frontend
  const consent = request.headers.get('cookie') ?? '';
  return consent.includes('gdpr_consent=1');
}
```

---

## 5. Audit Logging Geo-Block Events

Geo-enforcement only satisfies compliance if it is auditable. Write immutable geo-block events to
Analytics Engine (real-time) and R2 (durable) with enough context for a legal review.

```typescript
// src/telemetry/geo-events.ts

export async function emitGeoBlockEvent(
  env: Env,
  request: Request,
  country: string,
  reason: string
): Promise<void> {
  const now = Date.now();
  const url = new URL(request.url);

  // Analytics Engine for real-time alerting
  env.SECURITY_ANALYTICS.writeDataPoint({
    indexes: ['geo_block'],
    blobs: [
      'geo_block',
      country,
      reason.slice(0, 200),
      url.pathname.slice(0, 128),
      request.method,
    ],
    doubles: [now],
  });

  // R2 for durable compliance audit trail
  const key = `geo-blocks/${country}/${now}-${crypto.randomUUID()}.json`;
  await env.AUDIT_BUCKET.put(
    key,
    JSON.stringify({
      timestamp: new Date(now).toISOString(),
      country,
      reason,
      path: url.pathname,
      method: request.method,
      // no IP — GDPR; use request ID if Cloudflare provides one
    }),
    {
      httpMetadata: { contentType: 'application/json' },
      customMetadata: { retention: '7years', classification: 'compliance' },
    }
  );
}
```

---

## 6. Dynamic Policy Updates via KV

Legal requirements change. The KV override mechanism lets you update policies without redeployment:

```typescript
// src/admin/geo-policy-admin.ts

export async function updateCountryPolicy(
  env: Env,
  country: string,
  policy: unknown, // GeoPolicy shape
  expiresInSeconds = 86_400
): Promise<void> {
  if (!/^[A-Z]{2}$/.test(country)) {
    throw new Error('Invalid country code');
  }

  await env.GEO_POLICY_OVERRIDES.put(
    `country:${country}`,
    JSON.stringify(policy),
    { expirationTtl: expiresInSeconds }
  );
}
```

Protect the admin endpoint with service-token authentication (`cloudflare-access-service-token-rotation-and-emergency-revocation.md`).

---

## Anti-patterns

- **Reading `X-Country` or `CF-IPCountry` headers** — these can be injected by clients or intermediate
  proxies. Only `request.cf.country` is authoritative, set by Cloudflare's infrastructure.
- **Client-side geo-gating only** — JS-level country checks are trivially bypassed with a VPN. The
  Worker gate is the only enforceable boundary.
- **Blocking without a 451 response** — RFC 7725 specifies 451 (Unavailable For Legal Reasons) for
  legally mandated blocks. Using 403 obscures the reason and may complicate legal review.
- **Not logging geo-block events** — without an audit trail, you cannot prove to a regulator that
  enforcement was active during a given period.
- **Hardcoding the sanctions list in source code without a review process** — OFAC lists change.
  Include a dated comment, a review reminder, and link to the official source.

---

## Gotchas

- `request.cf` is `undefined` during local `wrangler dev` (without `--remote`). Always guard with
  `request.cf ?? {}` and default `country` to `'XX'`.
- Cloudflare's geolocation is based on IP; VPN and Tor exit nodes will show the exit node's country.
  This is an accepted limitation of IP-based geo enforcement — document it for your legal team.
- KV reads add ~1–5 ms latency per request. Cache the KV override in a module-level `Map` with a
  60-second TTL using `Date.now()` comparison, refreshed via `ctx.waitUntil()`.
- `request.cf.country` can return `'T1'` for Tor exit nodes and `'XX'` for unknown IPs. Treat both
  the same as your default policy unless your legal team specifies otherwise.
- The Cloudflare Smart Placement feature may route Workers to non-EU DCs for EU users. If data
  residency requires EU-only processing, enforce via `Smart Placement: disabled` and configure your
  Worker to deploy only to EU DCs using Worker locations.

---

## Verification

```bash
# 1. Simulate a sanctioned country request via curl with a spoofed CF header
#    (in production, Cloudflare overrides cf.country — this tests local dev behavior)
curl -si https://api.example.com/api/v2/posts \
  -H 'X-Simulated-Country: IR'

# 2. In production, test by querying from a VPN exit in a sanctioned country
#    and verifying the 451 response.

# 3. Query audit R2 bucket for geo-block events
wrangler r2 object list audit-bucket --prefix geo-blocks/IR/ | head -5

# 4. Verify AE telemetry
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT blob2 AS country, count() AS blocks FROM security_events WHERE index1 = '\''geo_block'\'' AND timestamp > now() - INTERVAL '\''1'\'' HOUR GROUP BY country ORDER BY blocks DESC"}'
```

---

## Related

- `workers-analytics-engine-security-telemetry.md`
- `workers-audit-log-immutable-r2-worm-pattern.md`
- `cloudflare-bot-management-abuse-prevention.md`
- `cloudflare-access-service-token-rotation-and-emergency-revocation.md`
- `zero-trust-network-architecture-ztna.md`

---

## Sources

- RFC 7725 — An HTTP Status Code to Report Legal Obstacles (451)
- Cloudflare Workers `request.cf` object — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- OFAC Sanctions List — https://ofac.treasury.gov/sanctions-list-service
- GDPR Chapter V — Transfers of Personal Data to Third Countries
- Cloudflare Geo-blocking best practices — https://developers.cloudflare.com/fundamentals/reference/geo-blocking/
- NetzDG (Network Enforcement Act) — Federal Ministry of Justice (Germany)
