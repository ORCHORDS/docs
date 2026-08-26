# Geographic-Aware Routing and Data Residency in Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You need to route users to the nearest database replica, serve localized content (language, currency, date format), or enforce data-residency regulations (GDPR, PIPL) by restricting which D1 or Durable Object handles a request based on the user's country or region.

## Context
Cloudflare Workers execute at the PoP closest to the user, and every `Request` carries a `cf` property populated by the Cloudflare network. This includes `cf.country` (ISO 3166-1 alpha-2), `cf.region`, `cf.city`, `cf.latitude`, `cf.longitude`, `cf.continent`, and `cf.timezone`. Durable Objects and D1 support regional placement (EU, APAC, ENAM, WNAM, OC), enabling true data-residency enforcement without a separate routing layer. Smart Placement (Durable Objects `locationHint`) moves the DO instance close to the data, not just the client.

## Reading Geographic Context
Access the `cf` object from the incoming request. It is populated automatically in production; in local dev it returns `undefined`.

```typescript
interface GeoContext {
  country: string;
  region: string | null;
  continent: string;
  timezone: string;
  latitude: string;
  longitude: string;
}

function getGeo(request: Request): GeoContext {
  const cf = request.cf ?? {};
  return {
    country:   (cf as Record<string, string>)['country']   ?? 'US',
    region:    (cf as Record<string, string>)['region']    ?? null,
    continent: (cf as Record<string, string>)['continent'] ?? 'NA',
    timezone:  (cf as Record<string, string>)['timezone']  ?? 'America/New_York',
    latitude:  (cf as Record<string, string>)['latitude']  ?? '37.77',
    longitude: (cf as Record<string, string>)['longitude'] ?? '-122.42',
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const geo = getGeo(request);
    return Response.json({ geo });
  },
};
```

## Routing to Regional D1 Databases
Bind multiple D1 databases (one per region) in `wrangler.toml` and select the correct one at runtime based on the user's country.

```toml
# wrangler.toml — multiple D1 bindings
[[d1_databases]]
binding = "DB_EU"
database_name = "app-eu"
database_id   = "<eu-db-id>"

[[d1_databases]]
binding = "DB_US"
database_name = "app-us"
database_id   = "<us-db-id>"

[[d1_databases]]
binding = "DB_APAC"
database_name = "app-apac"
database_id   = "<apac-db-id>"
```

```typescript
interface RegionalEnv {
  DB_EU: D1Database;
  DB_US: D1Database;
  DB_APAC: D1Database;
}

const EU_COUNTRIES = new Set([
  'AT','BE','BG','CY','CZ','DE','DK','EE','ES','FI','FR','GR','HR',
  'HU','IE','IT','LT','LU','LV','MT','NL','PL','PT','RO','SE','SI','SK',
]);

const APAC_COUNTRIES = new Set([
  'AU','CN','HK','ID','IN','JP','KR','MY','NZ','PH','SG','TH','TW','VN',
]);

function selectDatabase(env: RegionalEnv, country: string): D1Database {
  if (EU_COUNTRIES.has(country))   return env.DB_EU;
  if (APAC_COUNTRIES.has(country)) return env.DB_APAC;
  return env.DB_US; // default / AMER
}

export const regionalHandler = {
  async fetch(request: Request, env: RegionalEnv): Promise<Response> {
    const { country } = getGeo(request);
    const db = selectDatabase(env, country);

    const { results } = await db.prepare(
      'SELECT id, name FROM products WHERE active = 1 LIMIT 20',
    ).all();

    return Response.json({ country, products: results });
  },
};
```

## Data Residency Enforcement
Block or redirect requests from restricted countries before any data access; return a `451 Unavailable For Legal Reasons` status with an explanatory body.

```typescript
const DATA_RESTRICTED_COUNTRIES = new Set(['CN', 'RU', 'IR', 'KP']); // example

function enforceResidency(country: string, requestedRegion: string): Response | null {
  if (DATA_RESTRICTED_COUNTRIES.has(country)) {
    return new Response(
      JSON.stringify({
        error: 'service_unavailable',
        reason: 'Data residency restrictions prevent access from your location.',
        country,
      }),
      {
        status: 451,
        headers: {
          'Content-Type': 'application/json',
          'Link': '<https://example.com/legal/residency>; rel="blocked-by"',
        },
      },
    );
  }

  // Cross-region data request: EU user querying US data
  if (country && EU_COUNTRIES.has(country) && requestedRegion === 'US') {
    return Response.redirect('https://eu.example.com' + '/api', 307);
  }

  return null; // allowed
}
```

## Geo-Localized Content and Durable Object Placement
Use `locationHint` on Durable Object stubs to co-locate the DO with the user's continent, minimising cross-PoP latency for stateful sessions.

```typescript
type DOLocationHint = 'wnam' | 'enam' | 'sam' | 'weur' | 'eeur' | 'apac' | 'oc' | 'afr' | 'me';

function continentToHint(continent: string): DOLocationHint {
  const MAP: Record<string, DOLocationHint> = {
    EU: 'weur', AS: 'apac', OC: 'oc', SA: 'sam', AF: 'afr',
    NA: 'wnam', ME: 'me',
  };
  return MAP[continent] ?? 'wnam';
}

interface SessionEnv {
  USER_SESSION: DurableObjectNamespace;
}

export const sessionHandler = {
  async fetch(request: Request, env: SessionEnv): Promise<Response> {
    const geo = getGeo(request);
    const hint = continentToHint(geo.continent);
    const userId = request.headers.get('x-user-id') ?? 'anonymous';

    const id = env.USER_SESSION.idFromName(userId);
    const stub = env.USER_SESSION.get(id, { locationHint: hint });

    return stub.fetch(request);
  },
};
```

## Serving Locale-Specific Content
Resolve locale from the user's country and timezone for content negotiation without `Accept-Language` header dependency.

```typescript
interface Locale {
  language: string;
  currency: string;
  dateFormat: string;
}

const COUNTRY_LOCALE: Record<string, Locale> = {
  DE: { language: 'de-DE', currency: 'EUR', dateFormat: 'DD.MM.YYYY' },
  JP: { language: 'ja-JP', currency: 'JPY', dateFormat: 'YYYY/MM/DD' },
  US: { language: 'en-US', currency: 'USD', dateFormat: 'MM/DD/YYYY' },
  GB: { language: 'en-GB', currency: 'GBP', dateFormat: 'DD/MM/YYYY' },
  BR: { language: 'pt-BR', currency: 'BRL', dateFormat: 'DD/MM/YYYY' },
};

const DEFAULT_LOCALE: Locale = { language: 'en-US', currency: 'USD', dateFormat: 'MM/DD/YYYY' };

function resolveLocale(country: string): Locale {
  return COUNTRY_LOCALE[country] ?? DEFAULT_LOCALE;
}

export function buildLocalizedResponse(request: Request, data: unknown): Response {
  const { country } = getGeo(request);
  const locale = resolveLocale(country);

  return new Response(JSON.stringify({ locale, data }), {
    headers: {
      'Content-Type': 'application/json',
      'Content-Language': locale.language,
      'Vary': 'CF-IPCountry',
    },
  });
}
```

## Anti-patterns
- Using `cf.country` for security-critical access control without a fallback — `cf` values can be absent in local dev and can be spoofed via raw TCP on some non-Cloudflare paths; combine with JWT claims for authoritative geo checks.
- Hardcoding D1 binding names as strings — reference through the `env` type to get compile-time safety.
- Redirecting EU users to a different domain and then back within the same subrequest chain — creates redirect loops; resolve the correct region once at the edge and proxy internally.
- Caching geo-personalised responses at the edge without `Vary: CF-IPCountry` — different countries get the same cached body.
- Forgetting that `locationHint` is a soft hint, not a guarantee — Durable Objects may not be available at every hint location; the runtime falls back to the nearest available region.

## Gotchas
- `cf.country` returns `'T1'` for Tor exit nodes and `undefined` for loopback/local connections — handle both in your mapping functions.
- Smart Placement (`locationHint`) is available only on paid Durable Objects; on Workers Free it is silently ignored.
- D1 does not yet support per-row geo-replication; multi-region D1 means separate databases with application-level routing, not automatic sync.
- `EU_COUNTRIES` must be kept in sync with EU membership changes (e.g. Brexit already removed GB); drive this from a KV key for runtime updates.
- Using `cf.timezone` to infer locale is a heuristic, not authoritative; users can travel across borders. Always allow manual locale override via a cookie or user preference.

## Verification
1. Use `curl -H "CF-IPCountry: DE" https://your-worker.dev/api` in local Wrangler dev with a mocked `cf` object to verify EU routing.
2. Deploy to a preview environment and use a VPN exit node in Germany; confirm `DB_EU` receives the query in D1 logs.
3. Test the `451` flow from a restricted-country VPN; assert the response status and `Link` header match the spec.
4. Unit-test `selectDatabase`, `enforceResidency`, and `resolveLocale` with all edge-case country codes (`undefined`, `'T1'`, empty string).

## Related
- `/documentation/categories/patterns/per-tenant-durable-object.md`
- `/documentation/categories/patterns/multi-tenant-data-isolation.md`
- `/documentation/categories/patterns/session-management-workers.md`
- `/documentation/categories/patterns/cache-aside-kv-d1-fallback.md`

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/durable-objects/reference/smart-placement/
- https://developers.cloudflare.com/d1/platform/regions/
- https://www.rfc-editor.org/rfc/rfc7725 (HTTP 451)
