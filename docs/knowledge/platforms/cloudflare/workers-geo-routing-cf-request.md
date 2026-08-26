# Geographic Routing in Workers Using request.cf

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to serve locale-specific content, enforce regional compliance restrictions, or route traffic to the nearest origin based on where the visitor is located — all at the edge, before touching an origin server. Cloudflare Workers expose a rich `cf` object on every `Request` that carries country, continent, timezone, colo, and ASN data derived from Cloudflare's Anycast network without any extra API call.

---

## Context

The `request.cf` object is populated by Cloudflare's network for every inbound request and is available in all Workers runtimes. The `country` field is a two-letter ISO 3166-1 alpha-2 code; `continent` is a two-letter code (EU, NA, AS, AF, OC, SA, AN); `colo` is the three-letter IATA airport code of the Cloudflare data center that received the request. When an R2 bucket holds region-specific assets (EU/US variants of a page or image set), a Worker can pick the right prefix based on `cf.country` or `cf.continent` without a redirect. Geo-blocking with HTTP 451 ("Unavailable For Legal Reasons") is the standards-compliant status for content blocked due to legal obligations. Testing geo-logic locally requires the `--ip` flag in `wrangler dev` to simulate a specific source IP.

---

## Section 1 — Config / wrangler.toml

```toml
# wrangler.toml
name = "geo-router"
main = "src/index.ts"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding = "ASSETS"
bucket_name = "geo-assets"
```

---

## Section 2 — Worker implementation

```typescript
// src/index.ts
export interface Env {
  ASSETS: R2Bucket;
}

// Countries that are legally blocked from accessing the service
const BLOCKED_COUNTRIES = new Set(["KP", "IR", "SY", "CU"]);

// Map continents to R2 asset prefixes
const CONTINENT_PREFIX: Record<string, string> = {
  EU: "eu",
  NA: "us",
  AS: "apac",
  OC: "apac",
  SA: "latam",
  AF: "intl",
  AN: "intl",
};

function getLocalePrefix(cf: IncomingRequestCfProperties): string {
  return CONTINENT_PREFIX[cf.continent ?? ""] ?? "intl";
}

async function serveR2Asset(
  bucket: R2Bucket,
  prefix: string,
  path: string
): Promise<Response> {
  const key = `${prefix}${path}`; // e.g. "eu/index.html"
  const obj = await bucket.get(key);
  if (!obj) {
    // Fall back to the international variant
    const fallback = await bucket.get(`intl${path}`);
    if (!fallback) return new Response("Not found", { status: 404 });
    return new Response(fallback.body, {
      headers: {
        "Content-Type": fallback.httpMetadata?.contentType ?? "application/octet-stream",
        "X-Geo-Fallback": "true",
      },
    });
  }
  return new Response(obj.body, {
    headers: {
      "Content-Type": obj.httpMetadata?.contentType ?? "application/octet-stream",
      "X-Served-From": prefix,
      "X-Colo": (obj.customMetadata ?? {})["colo"] ?? "",
    },
  });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const cf = request.cf as IncomingRequestCfProperties | undefined;

    // --- Geo-block ---
    const country = cf?.country ?? "XX";
    if (BLOCKED_COUNTRIES.has(country)) {
      return new Response(
        JSON.stringify({ error: "This service is not available in your region." }),
        {
          status: 451, // Unavailable For Legal Reasons
          headers: {
            "Content-Type": "application/json",
            Link: '<https://www.rfc-editor.org/rfc/rfc7725>; rel="blocked-by"',
          },
        }
      );
    }

    // --- Continent-based routing ---
    const url = new URL(request.url);
    const prefix = getLocalePrefix(cf ?? ({} as IncomingRequestCfProperties));

    // Diagnostic endpoint — return all available cf fields
    if (url.pathname === "/_geo") {
      return Response.json({
        country: cf?.country,
        continent: cf?.continent,
        colo: cf?.colo,
        timezone: cf?.timezone,
        city: cf?.city,
        latitude: cf?.latitude,
        longitude: cf?.longitude,
        asn: cf?.asn,
        asOrganization: cf?.asOrganization,
        resolvedPrefix: prefix,
      });
    }

    // --- Serve locale-specific asset from R2 ---
    return serveR2Asset(env.ASSETS, prefix, url.pathname);
  },
};
```

---

## Section 3 — Colo-based nearest-origin routing (no R2)

```typescript
// If you're proxying to regional origins instead of R2:
const COLO_TO_ORIGIN: Record<string, string> = {
  // EMEA colos → EU origin
  LHR: "https://eu-origin.example.com",
  AMS: "https://eu-origin.example.com",
  CDG: "https://eu-origin.example.com",
  // APAC colos → APAC origin
  NRT: "https://apac-origin.example.com",
  SIN: "https://apac-origin.example.com",
  SYD: "https://apac-origin.example.com",
};

const DEFAULT_ORIGIN = "https://us-origin.example.com";

function pickOrigin(colo: string | undefined): string {
  return COLO_TO_ORIGIN[colo ?? ""] ?? DEFAULT_ORIGIN;
}

// Usage inside fetch():
// const origin = pickOrigin(cf?.colo);
// const upstream = new URL(request.url);
// upstream.hostname = new URL(origin).hostname;
// return fetch(new Request(upstream.toString(), request));
```

---

## Anti-patterns

- **Using IP-based geolocation libraries** — Downloading a MaxMind MMDB into the Worker bundle is megabytes of dead weight; `request.cf.country` is already resolved by Cloudflare's network at zero cost.
- **Returning 403 for geo-blocks instead of 451** — RFC 7725 reserves 451 specifically for legally-motivated unavailability; 403 conflates authorization failures with compliance blocks.
- **Caching geo-restricted responses at the edge without a Vary header** — If Cloudflare caches a blocked response and serves it to an unblocked user (or vice versa), add `Vary: CF-IPCountry` or use Cache API with a country-keyed cache key.
- **Hardcoding a fixed colo-to-origin map without a fallback** — Cloudflare has hundreds of colos; always have a default origin for unmapped colos.

---

## Gotchas

- `request.cf` is `undefined` in unit tests and in `wrangler dev` without the `--ip` flag; always guard with a null-coalesce.
- `cf.country` can be `"T1"` for Tor exit nodes — handle it explicitly if your compliance rules require it.
- The `continent` field is not in older `@cloudflare/workers-types` versions; update to ≥ 4.x or cast to `any` and validate at runtime.
- R2 `get()` returns `null` for missing keys (not an error); always check for null before reading `.body`.
- `wrangler dev --ip 91.108.4.1` simulates a Russian IP; pick IPs from the relevant country's allocation to test different `cf.country` values.

---

## Verification

```bash
# Start local dev simulating a UK IP
npx wrangler dev --ip 81.2.69.142

# Check geo diagnostic endpoint
curl http://localhost:8787/_geo
# Expected: {"country":"GB","continent":"EU","colo":"...","resolvedPrefix":"eu"}

# Simulate a blocked country (North Korea IP range)
npx wrangler dev --ip 175.45.176.1
curl http://localhost:8787/_geo
# Expected: 451 with JSON error body

# Deploy and test live
npx wrangler deploy
curl -H 'CF-Connecting-IP: 91.108.4.1' https://geo-router.example.workers.dev/_geo
```

---

## Related

- `workers-service-bindings-internal-api.md`
- `cloudflare-pages-incremental-static-regen.md`

---

## Sources

- Cloudflare Workers IncomingRequestCfProperties — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- RFC 7725: HTTP 451 — https://www.rfc-editor.org/rfc/rfc7725
- Cloudflare R2 Docs — https://developers.cloudflare.com/r2/
