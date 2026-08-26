# cloudflare-workers-geolocation-locale-routing

**Issue:** Automatic locale routing in Cloudflare Workers using
           cf.country and cf.timezone, with handling for mobile roaming,
           VPN false positives, and user-override persistence in KV
**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

Apps that serve multiple locales need to route new visitors to the
correct language/region without requiring them to pick manually.
Naive reliance on IP geolocation produces wrong results for users
on mobile roaming, VPNs, or corporate proxies.

## Context

Cloudflare Workers expose geolocation metadata on the `cf` object
of every incoming request.  This data is populated by Cloudflare's
IP intelligence at the edge and is available before the Worker
makes any origin request.  The canonical strategy is: check for an
explicit user preference first, fall back to geolocation, and store
confirmed preferences in KV for future requests.

## Available geolocation fields

```
┌────────────────────┬──────────────────────────────────────────┐
│ Field              │ Description                              │
├────────────────────┼──────────────────────────────────────────┤
│ cf.country         │ ISO 3166-1 alpha-2 country code          │
│ cf.region          │ Subdivision (state/province) name        │
│ cf.city            │ City name (English)                      │
│ cf.timezone        │ IANA timezone (e.g. "Europe/Berlin")     │
│ cf.continent       │ Two-letter continent code                │
│ cf.latitude        │ Approximate latitude (string)            │
│ cf.longitude       │ Approximate longitude (string)           │
│ cf.postalCode      │ Postal/ZIP code                          │
│ cf.isEUCountry     │ "1" if EU member state                   │
└────────────────────┴──────────────────────────────────────────┘
```

`cf.country` is available on all plans.  `cf.timezone` requires
at least the Workers Paid plan; it falls back to `undefined` on
free plans.

## Locale routing algorithm

```js
const SUPPORTED_LOCALES = ['en', 'de', 'fr', 'ja', 'ar'];
const DEFAULT_LOCALE    = 'en';

// Country → locale mapping (abbreviated)
const COUNTRY_LOCALE = {
  DE: 'de', AT: 'de', CH: 'de',
  FR: 'fr', BE: 'fr', LU: 'fr',
  JP: 'ja',
  SA: 'ar', AE: 'ar', EG: 'ar',
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // 1. Explicit user preference takes priority
    const storedLocale = await getStoredLocale(request, env);
    if (storedLocale) return redirect(url, storedLocale);

    // 2. Accept-Language header (higher signal than IP)
    const acceptLang = request.headers.get('accept-language') ?? '';
    const headerLocale = matchFromHeader(acceptLang, SUPPORTED_LOCALES);
    if (headerLocale) return redirect(url, headerLocale);

    // 3. Geolocation fallback
    const country = request.cf?.country ?? 'XX';
    const geoLocale = COUNTRY_LOCALE[country] ?? DEFAULT_LOCALE;
    return redirect(url, geoLocale);
  }
};

function redirect(url, locale) {
  url.pathname = `/${locale}${url.pathname}`;
  return Response.redirect(url.toString(), 302);
}
```

## Mobile roaming accuracy issues

Mobile roaming is the most common source of geolocation errors.  A
user physically in France using a German SIM roaming on a French
carrier may resolve to Germany (home network IP) or France (visited
network IP), depending on whether traffic is routed through the home
network.

Observed patterns:

```
┌─────────────────────────────┬──────────────────────────────────┐
│ Roaming scenario            │ cf.country result                │
├─────────────────────────────┼──────────────────────────────────┤
│ EU data roaming (default)   │ Home country (via home network)  │
│ EU "roam like at home"      │ Visited country or home country  │
│ US carrier abroad           │ Home carrier IP → US             │
│ LTE fallback on local SIM   │ Visited country                  │
└─────────────────────────────┴──────────────────────────────────┘
```

**Mitigation**: Weight `Accept-Language` above `cf.country` for
language selection.  Use geolocation only for region-specific
legal/currency defaults, not language.  Never hard-redirect users
to a locale they cannot change without a visible override control.

## VPN false positives

Commercial VPNs, privacy browsers (Brave with "Aggressive" shields),
and mobile VPN apps (NordVPN mobile, Cloudflare WARP) exit through
servers in arbitrary countries.  `cf.country` reflects the VPN exit
node, not the user's physical location.

Detection heuristic: if `cf.country` disagrees with the primary
language in `Accept-Language` by a large margin (e.g. `cf.country=US`
but `Accept-Language: de-DE,de;q=0.9`), treat the language header as
more authoritative and log the discrepancy for monitoring.

```js
function detectVpnMismatch(cfCountry, acceptLang) {
  const headerLang = acceptLang.split(',')[0].split('-')[0];
  const expectedLang = COUNTRY_LOCALE[cfCountry]?.split('-')[0];
  return expectedLang && headerLang !== expectedLang;
}
```

Cloudflare also provides `cf.asn` and `cf.asOrganization`; known
VPN ASNs can be blocklisted for stricter enforcement contexts
(not recommended for locale routing — too blunt).

## User override persistence in KV

When a user explicitly selects a locale, persist the preference in
KV keyed by a session token stored in a cookie.

```js
const PREF_TTL = 365 * 24 * 3600; // 1 year in seconds

async function saveLocalePreference(request, locale, env) {
  let token = getCookie(request, 'pref_token');
  if (!token) {
    token = crypto.randomUUID();
  }
  await env.PREFS_KV.put(`locale:${token}`, locale, {
    expirationTtl: PREF_TTL,
  });
  return token;
}

async function getStoredLocale(request, env) {
  const token = getCookie(request, 'pref_token');
  if (!token) return null;
  return env.PREFS_KV.get(`locale:${token}`);
}

// Set on preference save endpoint
function setPreferenceCookie(response, token) {
  response.headers.append('Set-Cookie',
    `pref_token=${token}; Path=/; Max-Age=${PREF_TTL}; `
    + `SameSite=Lax; Secure`
  );
}
```

KV read latency on Cloudflare's edge is typically 1–5 ms for keys
with recent reads (in-region cache hit); cold reads are 10–30 ms.
For high-traffic sites, use a 5–10 s in-memory cache inside the
Worker instance to avoid KV reads on every request.

## Timezone-based locale refinement

`cf.timezone` provides the IANA timezone string.  This is useful for
formatting defaults (date format, week start) even when the language
is already known from `Accept-Language`.

```js
function localeOptionsFromTimezone(timezone) {
  // Derive currency and date format region from timezone
  if (!timezone) return {};
  const [continent, city] = timezone.split('/');
  if (continent === 'America' && ['New_York','Chicago',
      'Denver','Los_Angeles'].includes(city)) {
    return { currency: 'USD', dateFormat: 'MDY' };
  }
  if (continent === 'Europe') {
    return { dateFormat: 'DMY' };
  }
  return {};
}
```

## Anti-patterns

- Issuing a permanent (301) redirect based on geolocation — 301s are
  cached by browsers; if the user's IP changes (roaming, VPN, travel)
  the browser stays stuck on the wrong locale forever.  Use 302.
- Storing the locale directly in the URL path without an override
  mechanism — users who land on `/de/` via redirect should always be
  able to switch to `/en/` and have that preference remembered.
- Relying solely on `cf.country` for legal compliance routing
  (GDPR consent, age-gating) — VPN users and roaming users bypass it.
  Use it as a default, not a gate.
- Caching locale-redirected responses in Cloudflare's CDN without
  `Vary: Cookie` — a cached German-locale redirect gets served to
  every English user for that URL until the cache expires.

## Gotchas

- `cf` fields are `undefined` in local `wrangler dev` unless you
  pass `--remote`; mock them in tests with `{ country: 'DE' }`.
- `cf.country` is `"T1"` for Tor exit nodes, not a real country code.
- `cf.timezone` can be `undefined` even on paid plans if the IP is
  too ambiguous (satellite, anonymous proxies); always guard with
  `?? 'UTC'`.
- The `cf` object is not available on subrequests made with `fetch()`
  inside the Worker; only the incoming request from the client carries
  the `cf` data.

## Verification

```bash
# Test geolocation from a specific country (use --remote)
curl -H "CF-IPCountry: DE" https://example.com/
# Should redirect to /de/

# Confirm KV preference storage
wrangler kv:key get --binding PREFS_KV "locale:$(cat /tmp/test_token)"

# Test Accept-Language override beats geo
curl -H "Accept-Language: fr,fr-FR;q=0.9" \
     -H "CF-IPCountry: JP" \
     https://example.com/
# Should redirect to /fr/, not /ja/
```

## Related

- `documentation/categories/i18n/locale-detection-browser.md`
- `documentation/categories/i18n/locale-negotiation-accept-language.md`
- `documentation/categories/i18n/locale-persistence-cookies-storage-2026.md`
- `documentation/categories/i18n/content-negotiation-vary-header.md`
- `documentation/categories/i18n/locale-fallback-chain.md`

## Source URLs

- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/workers/examples/geolocation-hello-world/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- https://datatracker.ietf.org/doc/html/rfc4647  (BCP 47 matching)
