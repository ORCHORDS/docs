# Geolocation API and Cloudflare Workers Edge Personalization

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
You need to personalize content by location — showing local pricing, nearby stores, region-specific compliance disclaimers, or localized date formats — without forcing users through a slow client-side permission prompt on every page load. The goal is to combine Cloudflare Workers' free edge geolocation (from request headers) for first-paint personalization with the browser's `Geolocation` API for precise opt-in location features.

## Context
Cloudflare Workers automatically annotate every incoming request with country, region, city, latitude, longitude, and postal code data available on the `request.cf` object — no API key required, no added latency. This coarse data is sufficient for most personalization needs (currency, language, tax region) and requires no user permission. The browser `Geolocation` API provides GPS-accurate coordinates but requires explicit user permission, triggers a browser dialog, and only works on HTTPS origins. The best pattern combines both: use `request.cf` at the edge for fast first-paint, then optionally refine with `Geolocation` for precise features (map centering, store finder).

## Edge Geolocation in Workers: First-Paint Personalization

```typescript
// workers/geo-personalize.ts
import { Env } from "./types";

interface GeoContext {
  country: string;
  countryName: string;
  region: string;
  city: string;
  latitude: number | null;
  longitude: number | null;
  postalCode: string;
  timezone: string;
  currency: string;
}

const COUNTRY_CURRENCY: Record<string, string> = {
  US: "USD", GB: "GBP", DE: "EUR", FR: "EUR",
  JP: "JPY", CA: "CAD", AU: "AUD", IN: "INR",
  BR: "BRL", MX: "MXN", KR: "KRW", CN: "CNY",
};

export function extractGeoContext(request: Request): GeoContext {
  const cf = (request as Request & { cf?: CfProperties }).cf ?? {};

  const country = String(cf.country ?? "US");
  const currency = COUNTRY_CURRENCY[country] ?? "USD";

  return {
    country,
    countryName: String(cf.country ?? "United States"),
    region: String(cf.region ?? ""),
    city: String(cf.city ?? ""),
    latitude: typeof cf.latitude === "number" ? cf.latitude : null,
    longitude: typeof cf.longitude === "number" ? cf.longitude : null,
    postalCode: String(cf.postalCode ?? ""),
    timezone: String(cf.timezone ?? "UTC"),
    currency,
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api/geo") {
      const geo = extractGeoContext(request);
      return new Response(JSON.stringify(geo), {
        headers: {
          "Content-Type": "application/json",
          // Edge geo data is cheap — cache briefly but revalidate per IP range
          "Cache-Control": "private, max-age=300",
          "Vary": "CF-IPCountry",
        },
      });
    }

    return env.ASSETS.fetch(request);
  },
};
```

## Injecting Geo Context into HTML at the Edge

For zero-latency first paint, inject the geo context directly into the HTML response using `HTMLRewriter` so the React app can read it synchronously.

```typescript
// workers/geo-injector.ts
import { Env } from "./types";
import { extractGeoContext } from "./geo-personalize";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const response = await env.ASSETS.fetch(request);

    if (!response.headers.get("Content-Type")?.includes("text/html")) {
      return response;
    }

    const geo = extractGeoContext(request);
    const geoScript = `<script id="__GEO_CONTEXT__" type="application/json">${
      JSON.stringify(geo)
    }</script>`;

    return new HTMLRewriter()
      .on("head", {
        element(el) {
          el.prepend(geoScript, { html: true });
        },
      })
      .transform(response);
  },
};
```

## React: Reading Edge Geo Context Without a Fetch

```tsx
// lib/geo-context.ts
export interface GeoContext {
  country: string;
  countryName: string;
  region: string;
  city: string;
  latitude: number | null;
  longitude: number | null;
  postalCode: string;
  timezone: string;
  currency: string;
}

export function readEdgeGeo(): GeoContext | null {
  if (typeof document === "undefined") return null;
  const el = document.getElementById("__GEO_CONTEXT__");
  if (!el) return null;
  try {
    return JSON.parse(el.textContent ?? "") as GeoContext;
  } catch {
    return null;
  }
}

// Fallback defaults when geo is unavailable
export const DEFAULT_GEO: GeoContext = {
  country: "US",
  countryName: "United States",
  region: "",
  city: "",
  latitude: null,
  longitude: null,
  postalCode: "",
  timezone: "America/New_York",
  currency: "USD",
};
```

```tsx
// contexts/GeoContext.tsx
import { createContext, useContext, ReactNode, useMemo } from "react";
import { GeoContext, readEdgeGeo, DEFAULT_GEO } from "@/lib/geo-context";

const Ctx = createContext<GeoContext>(DEFAULT_GEO);

export function GeoProvider({ children }: { children: ReactNode }) {
  const geo = useMemo(() => readEdgeGeo() ?? DEFAULT_GEO, []);
  return <Ctx.Provider value={geo}>{children}</Ctx.Provider>;
}

export const useGeo = () => useContext(Ctx);
```

## Browser Geolocation API: Precise Opt-In Location

```tsx
// hooks/usePreciseLocation.ts
import { useState, useCallback } from "react";
import { useGeo } from "@/contexts/GeoContext";

interface PreciseLocation {
  latitude: number;
  longitude: number;
  accuracy: number;
  source: "gps" | "edge";
}

interface PreciseLocationState {
  location: PreciseLocation | null;
  status: "idle" | "requesting" | "granted" | "denied" | "unavailable";
  error?: string;
}

export function usePreciseLocation() {
  const edgeGeo = useGeo();
  const [state, setState] = useState<PreciseLocationState>({
    // Pre-seed with coarse edge coordinates so the UI can render immediately
    location:
      edgeGeo.latitude !== null && edgeGeo.longitude !== null
        ? {
            latitude: edgeGeo.latitude,
            longitude: edgeGeo.longitude,
            accuracy: 50_000, // ~50 km — typical IP-to-geo accuracy
            source: "edge",
          }
        : null,
    status: "idle",
  });

  const requestPrecise = useCallback(() => {
    if (!("geolocation" in navigator)) {
      setState((s) => ({ ...s, status: "unavailable" }));
      return;
    }

    setState((s) => ({ ...s, status: "requesting" }));

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setState({
          location: {
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            accuracy: pos.coords.accuracy,
            source: "gps",
          },
          status: "granted",
        });
      },
      (err) => {
        setState((s) => ({
          ...s,
          status: err.code === GeolocationPositionError.PERMISSION_DENIED
            ? "denied"
            : "unavailable",
          error: err.message,
        }));
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 60_000 }
    );
  }, []);

  return { ...state, requestPrecise };
}
```

## Sending Precise Location to Workers for Nearest-Store Lookup

```typescript
// lib/store-finder.ts
interface Store {
  id: string;
  name: string;
  address: string;
  distanceKm: number;
}

export async function findNearestStores(
  lat: number,
  lon: number,
  radiusKm = 50
): Promise<Store[]> {
  // Send coordinates to the Worker which queries D1 using a bounding box
  const res = await fetch(
    `/api/stores/nearby?lat=${lat}&lon=${lon}&radius=${radiusKm}`,
    {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    }
  );
  if (!res.ok) throw new Error(`Store lookup failed: ${res.status}`);
  return res.json();
}
```

```typescript
// workers/stores-nearby.ts — D1 bounding-box query
export async function handleNearbyStores(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const lat = parseFloat(url.searchParams.get("lat") ?? "");
  const lon = parseFloat(url.searchParams.get("lon") ?? "");
  const radius = parseFloat(url.searchParams.get("radius") ?? "50");

  if (isNaN(lat) || isNaN(lon)) {
    return new Response(JSON.stringify({ error: "Invalid coordinates" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Haversine approximation: 1 degree lat ≈ 111 km
  const latDelta = radius / 111;
  const lonDelta = radius / (111 * Math.cos((lat * Math.PI) / 180));

  const { results } = await env.DB.prepare(`
    SELECT id, name, address, lat, lon,
      (6371 * acos(
        cos(radians(?)) * cos(radians(lat)) *
        cos(radians(lon) - radians(?)) +
        sin(radians(?)) * sin(radians(lat))
      )) AS distance_km
    FROM stores
    WHERE lat BETWEEN ? AND ?
      AND lon BETWEEN ? AND ?
    ORDER BY distance_km
    LIMIT 10
  `)
    .bind(lat, lon, lat, lat - latDelta, lat + latDelta, lon - lonDelta, lon + lonDelta)
    .all<{ id: string; name: string; address: string; distance_km: number }>();

  return new Response(JSON.stringify(results), {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "private, max-age=60",
    },
  });
}
```

## Anti-patterns

- **Using `request.cf` latitude/longitude as GPS-accurate coordinates** — Edge geo is IP-based and can be off by dozens of kilometres. Never use it to show a map pin or calculate precise driving distances; use it only for country/region-level personalization.
- **Caching geo-personalized HTML at the CDN edge** — If you embed city or currency into HTML, set `Cache-Control: private` or vary on `CF-IPCountry` to avoid serving New York pricing to Tokyo users.
- **Requesting geolocation on page load without a user gesture** — Browsers require a user-initiated event to trigger the permission prompt. Auto-requesting on mount causes denials and browser warnings.
- **Not providing a fallback when `request.cf` is undefined** — `request.cf` is absent in local `wrangler dev` and in some testing environments. Default all fields gracefully.
- **Sending raw GPS coordinates to a third-party API from the client** — Route coordinates through your Workers proxy so you can rate-limit, validate, and avoid exposing third-party API keys to the browser.

## Gotchas

- **`request.cf.timezone` reflects the data center's assigned timezone for the IP, not the user's device timezone** — A mobile user on a corporate VPN will get the VPN exit node's timezone. Use `Intl.DateTimeFormat().resolvedOptions().timeZone` from the browser for the actual device timezone.
- **`CF-IPCountry` header vs `request.cf.country`** — They are the same value but `request.cf.country` is only available inside Workers; `CF-IPCountry` is available in Pages Functions and Middleware. Use the appropriate accessor.
- **Geolocation watchPosition battery drain** — `navigator.geolocation.watchPosition()` keeps the GPS radio active. Always call `clearWatch()` in cleanup; for store-finder use cases, a single `getCurrentPosition` is sufficient.
- **D1 does not have a native trigonometric haversine function** — The pure-SQL haversine in the example works but requires an `acos`/`cos`/`sin`/`radians` function chain that D1's SQLite engine supports. Test on real D1 — not on a local SQLite fork — since some function sets differ.
- **`maximumAge` in `getCurrentPosition` options** — Setting a high `maximumAge` (60 seconds) avoids redundant GPS reads on repeat calls. Do not set it to 0 if the user is stationary.

## Verification

1. Deploy the Workers geo endpoint and call `/api/geo` from two different VPN exit nodes (e.g., UK and Germany); confirm `country`, `currency`, and `timezone` differ.
2. Inspect the HTML source of a Pages response and confirm `<script id="__GEO_CONTEXT__">` is present in `<head>` with valid JSON.
3. Open the React app, verify `useGeo().currency` returns the correct currency for your current IP without a network request.
4. Click "Find nearby stores", grant geolocation permission, and confirm the returned stores are sorted by ascending `distance_km`.
5. Test with `wrangler dev` and confirm `request.cf` fallback to defaults does not throw.

## Related

- `edge-middleware-i18n-routing-cloudflare-pages.md` — routing by country at the edge
- `dark-mode-edge-cookie-cloudflare-pages.md` — injecting user preferences via HTMLRewriter
- `temporal-api-date-formatting-cloudflare-pages.md` — using the edge timezone for date formatting
- `indexeddb-offline-sync-cloudflare-d1-workers.md` — D1 query patterns from Workers

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API
- https://developers.cloudflare.com/workers/examples/geolocation-hello-world/
