# Cloudflare Managed Transforms — True-Client-IP, Geo Headers, and Server Identity Stripping

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your Workers origin or downstream service needs reliable visitor IP, geographic metadata, or bot-score data in request headers — without writing Transform Rules for each one. Alternatively, your HTTP responses expose `Server` and `X-Powered-By` headers that leak implementation details, and you need them stripped at the edge without touching origin code.

## Context

Cloudflare Managed Transforms are zone-level header rules maintained by Cloudflare. They are toggled on/off in the dashboard or via API and execute before any Worker, Page Rule, or custom Transform Rule. Two categories exist: **Managed Request Headers** (add information to inbound requests) and **Managed Response Headers** (add or remove information from outbound responses). Workers receive the already-transformed request; they must not attempt to re-add what Managed Transforms already inject.

## 1 — Enabling Managed Transforms via API

```typescript
// Enable "Add True-Client-IP header" and "Add visitor location headers"
interface Env { CF_API_TOKEN: string; ZONE_ID: string; }

async function enableManagedTransforms(env: Env): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/zones/${env.ZONE_ID}/managed_headers`;

  const payload = {
    managed_request_headers: [
      { id: 'add_true_client_ip_headers', enabled: true },
      { id: 'add_visitor_location_headers', enabled: true },
      { id: 'add_bot_protection_headers', enabled: true },
    ],
    managed_response_headers: [
      { id: 'remove_x-powered-by_header', enabled: true },
      { id: 'add_security_headers', enabled: true },
    ],
  };

  const res = await fetch(url, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) throw new Error(`Managed Transforms update failed: ${await res.text()}`);
}
```

## 2 — Reading Managed Request Headers in Workers

```typescript
interface GeoInfo {
  ip: string;
  country: string | null;
  city: string | null;
  region: string | null;
  latitude: string | null;
  longitude: string | null;
  timezone: string | null;
  botScore: string | null;
}

export function parseGeoHeaders(request: Request): GeoInfo {
  return {
    // True-Client-IP requires Business+ plan; CF-Connecting-IP is always present
    ip: request.headers.get('True-Client-IP')
     ?? request.headers.get('CF-Connecting-IP')
     ?? 'unknown',
    country:   request.headers.get('CF-IPCountry'),
    city:      request.headers.get('CF-IPCity'),
    region:    request.headers.get('CF-IPRegion'),
    latitude:  request.headers.get('CF-IPLatitude'),
    longitude: request.headers.get('CF-IPLongitude'),
    timezone:  request.headers.get('CF-Timezone'),
    botScore:  request.headers.get('CF-Bot-Score'),
  };
}

export default {
  async fetch(request: Request): Promise<Response> {
    const geo = parseGeoHeaders(request);
    return Response.json(geo);
  },
};
```

## 3 — Preferring request.cf Over HTTP Headers for Geo Data

`request.cf` is populated by the Workers runtime directly from Cloudflare's internal data — it is more reliable than the HTTP headers added by Managed Transforms, which can be spoofed if Managed Transforms are not yet enabled or if the request bypasses the zone (e.g., direct-to-origin).

```typescript
export default {
  async fetch(request: Request): Promise<Response> {
    const cf = request.cf;

    const geo = {
      // Always prefer request.cf — set by the runtime, not a header
      country:   cf?.country   ?? request.headers.get('CF-IPCountry')   ?? null,
      city:      cf?.city      ?? request.headers.get('CF-IPCity')      ?? null,
      timezone:  cf?.timezone  ?? request.headers.get('CF-Timezone')    ?? null,
      asn:       cf?.asn,
      colo:      cf?.colo,     // PoP IATA code
      tlsVersion: cf?.tlsVersion,
    };

    return Response.json(geo);
  },
};
```

## 4 — Stripping Server Identity Headers from Responses

```typescript
// Even when Managed Transforms handle Server/X-Powered-By, use this in Workers
// for defence-in-depth or for headers Managed Transforms do not cover.
function stripServerHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  headers.delete('Server');
  headers.delete('X-Powered-By');
  headers.delete('X-AspNet-Version');
  headers.delete('X-Generator');

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = await fetch(request);
    return stripServerHeaders(origin);
  },
};
```

## 5 — Adding Security Response Headers via Managed Transforms

The `add_security_headers` managed transform adds a baseline set of security headers (HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy). Verify they are set and add stricter values where needed.

```typescript
function enforceSecurityHeaders(response: Response): Response {
  const headers = new Headers(response.headers);

  // Managed Transforms adds HSTS max-age=15552000; upgrade here if needed
  if (!headers.has('Strict-Transport-Security')) {
    headers.set('Strict-Transport-Security', 'max-age=63072000; includeSubDomains; preload');
  }

  // Override with a stricter CSP if the managed one is too permissive
  headers.set(
    'Content-Security-Policy',
    "default-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'",
  );

  return new Response(response.body, { ...response, headers });
}
```

## 6 — Auditing Current Managed Transforms via API

```typescript
async function listManagedTransforms(zoneId: string, apiToken: string): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/managed_headers`,
    { headers: { Authorization: `Bearer ${apiToken}` } },
  );
  const data = await res.json<{
    result: {
      managed_request_headers: { id: string; enabled: boolean }[];
      managed_response_headers: { id: string; enabled: boolean }[];
    };
  }>();

  const enabled = [
    ...data.result.managed_request_headers,
    ...data.result.managed_response_headers,
  ].filter(h => h.enabled).map(h => h.id);

  console.log('Enabled Managed Transforms:', enabled);
}
```

## Anti-patterns

- **Manually adding `X-Forwarded-For` in a Worker when True-Client-IP or CF-Connecting-IP is already present** — creates a duplicate chain that confuses downstream log parsers.
- **Setting `Server: nginx` or `Server: Apache` in origin responses and relying on Managed Transforms to strip it** — test the strip is actually working; some origins set headers after the Managed Transform window.
- **Enabling all managed transforms without testing downstream impact** — `add_visitor_location_headers` adds ~8 headers; parsers that reject unknown headers on the origin will break.
- **Reading `CF-IPCountry` as an anti-fraud signal without `request.cf.country` fallback** — a request that reaches your Worker without traversing the zone edge (e.g., localhost dev, direct IP) will not have the header.

## Gotchas

- **True-Client-IP requires Business plan or above.** On lower plans the header is not injected even when the toggle is on; `CF-Connecting-IP` is available on all plans.
- Managed Transforms run **before** custom Transform Rules and before Workers; a Worker that sets the same header the Managed Transform adds will overwrite it in the response path but sees the Managed Transform value in the request path.
- In `wrangler dev`, Managed Transforms are not simulated; test with `wrangler dev --remote` or against the deployed zone.
- The `CF-Bot-Score` header (from `add_bot_protection_headers`) is only populated when Bot Management is enabled on the zone; on zones with only Bot Fight Mode, the header is absent.
- Managed Response Transforms execute after the Worker returns a response; a Worker cannot read the final state of Managed Response headers — only the state it set itself.

## Verification

```bash
# Confirm headers are present on a live request
curl -sI https://your-zone.example.com/ | grep -E 'True-Client-IP|CF-IPCountry|CF-Bot-Score|Server|X-Powered-By'
# True-Client-IP and CF-IPCountry should appear; Server and X-Powered-By should be absent
```

## Related

- `csp-headers-and-cf-waf.md`
- `workers-fetch-api-patterns.md`
- `browser-integrity-hotlink-email-toggles.md`
- `waf-managed-rules-exception-order-and-future-rule-drift.md`
- `geolocation-accuracy-mobile-carrier-roaming.md`

## Sources

- https://developers.cloudflare.com/rules/transform/managed-transforms/
- https://developers.cloudflare.com/rules/transform/managed-transforms/reference/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/fundamentals/reference/http-request-headers/
