# Cloudflare Pages Middleware Geo-Blocking

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to restrict access to a Pages application by country — either blocking a deny-list of regions or allowing only a permitted set — without deploying a full Workers service.

## Context
Cloudflare Pages Functions support a `_middleware.ts` file at any directory level. When placed at the root of `functions/`, it runs on every request before any route handler. The `request.cf` object (type `IncomingRequestCfProperties`) is available inside Functions and carries the visitor's `country` ISO-3166-1 alpha-2 code derived from Cloudflare's IP geolocation database. Pages Functions middleware compose via `next()` exactly like Workers middleware chains.

## Architecture / Setup

Project layout:
```
my-pages-app/
  functions/
    _middleware.ts   ← runs on every Pages Function request
  public/
    index.html
```

`wrangler.toml` (Pages project, no special geo config needed — CF geo is automatic):
```toml
name = "my-pages-app"
pages_build_output_dir = "public"
compatibility_date = "2025-09-01"
```

## Allow-list Middleware

`functions/_middleware.ts` — permit only listed countries, redirect everyone else:
```typescript
import type { PagesFunction } from "@cloudflare/workers-types";

const ALLOWED_COUNTRIES = new Set(["US", "CA", "GB", "AU", "NZ"]);
const BLOCKED_REDIRECT = "https://example.com/not-available";

export const onRequest: PagesFunction = async (context) => {
  const { request, next } = context;
  const cf = request.cf as IncomingRequestCfProperties | undefined;

  // cf may be undefined in local dev — allow through
  if (!cf) return next();

  const country = (cf.country ?? "") as string;

  if (!ALLOWED_COUNTRIES.has(country)) {
    // Return a 451 Unavailable For Legal Reasons with a redirect body
    return new Response(null, {
      status: 302,
      headers: {
        Location: BLOCKED_REDIRECT,
        "Cache-Control": "no-store",
        "CF-Country": country,
      },
    });
  }

  return next();
};
```

## Deny-list Middleware with Custom Error Page

`functions/_middleware.ts` — block a specific set of countries and serve an inline error:
```typescript
import type { PagesFunction } from "@cloudflare/workers-types";

const DENIED_COUNTRIES = new Set(["XX", "YY"]); // replace with real ISO codes

const blockedHtml = (country: string) => `<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Not Available</title></head>
<body>
  <h1>Service Not Available in Your Region</h1>
  <p>This service is not available in <strong>${country}</strong> at this time.</p>
</body>
</html>`;

export const onRequest: PagesFunction = async (context) => {
  const { request, next } = context;
  const cf = request.cf as IncomingRequestCfProperties | undefined;

  if (!cf) return next();

  const country = (cf.country ?? "") as string;

  if (DENIED_COUNTRIES.has(country)) {
    return new Response(blockedHtml(country), {
      status: 451,
      headers: {
        "Content-Type": "text/html;charset=UTF-8",
        "Cache-Control": "no-store",
        Vary: "CF-IPCountry",
      },
    });
  }

  const response = await next();
  // Stamp country on the way out for downstream telemetry
  const newHeaders = new Headers(response.headers);
  newHeaders.set("X-Visitor-Country", country);
  return new Response(response.body, {
    status: response.status,
    headers: newHeaders,
  });
};
```

## Scoped Middleware Per Sub-path

Place a `_middleware.ts` inside a subdirectory to scope blocking to a route prefix only:
```
functions/
  _middleware.ts          ← global: logs every request
  admin/
    _middleware.ts        ← blocks non-US traffic to /admin/*
    index.ts
```

`functions/admin/_middleware.ts`:
```typescript
import type { PagesFunction } from "@cloudflare/workers-types";

export const onRequest: PagesFunction = async ({ request, next }) => {
  const cf = request.cf as IncomingRequestCfProperties | undefined;
  const country = cf?.country ?? "";

  if (country !== "US") {
    return new Response("Admin access restricted to US only.", { status: 403 });
  }
  return next();
};
```

Middleware stacks: global `_middleware.ts` runs first, then the scoped one. Both must call `next()` for the chain to proceed.

## Anti-patterns
- **Caching geo-restricted responses at the edge** — always set `Cache-Control: no-store` or `Vary: CF-IPCountry` so Cloudflare's cache doesn't serve a blocked response to a different country.
- **Using `X-Forwarded-For` for country detection** — the `request.cf.country` field is authoritative; header-based detection is spoofable.
- **Blocking in static asset responses** — `_middleware.ts` only intercepts Pages Function routes (dynamic). Static files in `/public` bypass it unless you use a catch-all function `functions/[[path]].ts`.
- **Hard-coding country codes as strings** — use a `Set` for O(1) lookup; linear array search slows with large deny-lists.
- **Returning 403 without a body** — some CDN health checks and WAF scanners log empty 403s as anomalies; return a descriptive body or redirect.

## Gotchas
- In `wrangler pages dev`, `request.cf` is `undefined`; always guard with a null check and allow traffic through in development.
- The `country` field returns `"T1"` for Tor exit nodes and `"XX"` for unknown IPs — include these in deny-lists if your compliance policy requires it.
- Pages Functions middleware files must be named exactly `_middleware.ts` (or `.js`); any other name is treated as a route handler.
- If you deploy a catch-all `functions/[[path]].ts` alongside middleware, ensure it calls `env.ASSETS.fetch(request)` to serve static files; otherwise static assets return 404.
- `request.cf.country` reflects the connecting IP after Cloudflare's proxy unwrapping — it is not affected by VPNs the user runs unless those VPNs use Cloudflare IPs.

## Verification
```bash
# Test that a request from a blocked country returns 451
curl -s -o /dev/null -w "%{http_code}" \
  -H "CF-IPCountry: XX" \
  https://your-pages-app.pages.dev/

# Confirm the Vary header is set (prevents geo-split caching bugs)
curl -I https://your-pages-app.pages.dev/ | grep -i vary

# Local dev: middleware passthrough (cf undefined)
wrangler pages dev ./public --compatibility-date=2025-09-01
```

## Related
- [pages-functions-middleware.md](pages-functions-middleware.md)
- [pages-functions-routing.md](pages-functions-routing.md)
- [workers-geolocation-mobile-roaming-accuracy.md](workers-geolocation-mobile-roaming-accuracy.md)
- [geolocation-accuracy-mobile-carrier-roaming.md](geolocation-accuracy-mobile-carrier-roaming.md)
- [icloud-private-relay-geolocation-rate-limiting.md](icloud-private-relay-geolocation-rate-limiting.md)

## Sources
- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developers.cloudflare.com/pages/functions/routing/
- https://developers.cloudflare.com/cache/concepts/cache-control/
