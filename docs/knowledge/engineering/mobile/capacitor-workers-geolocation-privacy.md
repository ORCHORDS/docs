# Capacitor Geolocation + Cloudflare Workers Privacy Middleware

**Date:** 2026-08-23
**Author:** example.com
**Status:** production

---

## Symptom / Use-Case

Your Capacitor app collects geolocation coordinates and sends them to an API. You need to avoid logging raw GPS coordinates in server logs, strip precision before storing, enforce per-user consent checks at the edge, and satisfy GDPR/CCPA requirements without baking compliance logic into every mobile release. You want a Cloudflare Worker to act as a privacy proxy between the device and your data store.

---

## Context

Raw latitude/longitude coordinates are "personal data" under GDPR and "precise geolocation" under CCPA — both requiring explicit consent and data minimisation. Enforcing this in every mobile client is fragile; enforcement belongs at the API boundary. A Cloudflare Worker can reduce coordinate precision to the legally sufficient level, validate that a consent record exists before accepting the payload, and strip PII from logs before forwarding to your origin.

`@capacitor/geolocation` provides the native location API. The Worker receives coordinates, applies truncation to ~1 km grid (3 decimal places), checks a KV consent record, then forwards a sanitised payload to your origin.

---

## 1. Capacitor Geolocation Capture

```typescript
// src/location/capture.ts
import { Geolocation } from "@capacitor/geolocation";

export interface RawCoord {
  lat: number;
  lng: number;
  accuracy: number;
  timestamp: number;
}

export async function captureOnce(): Promise<RawCoord> {
  const perm = await Geolocation.checkPermissions();
  if (perm.location === "denied") {
    throw new Error("Location permission denied");
  }
  if (perm.location === "prompt") {
    const req = await Geolocation.requestPermissions({ permissions: ["location"] });
    if (req.location !== "granted") throw new Error("Permission not granted");
  }

  const pos = await Geolocation.getCurrentPosition({
    enableHighAccuracy: false, // coarse is sufficient after server-side truncation
    timeout: 10_000,
  });

  return {
    lat: pos.coords.latitude,
    lng: pos.coords.longitude,
    accuracy: pos.coords.accuracy,
    timestamp: pos.timestamp,
  };
}
```

---

## 2. Client — Send to Privacy Proxy Worker

```typescript
// src/location/reporter.ts
import { captureOnce } from "./capture";

const PRIVACY_PROXY = "https://geo-privacy.example.workers.dev/location";

export async function reportLocation(
  userId: string,
  sessionToken: string
): Promise<void> {
  const coord = await captureOnce();

  const res = await fetch(PRIVACY_PROXY, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${sessionToken}`,
      "X-User-Id": userId,
    },
    body: JSON.stringify(coord),
  });

  if (!res.ok) {
    const { error } = await res.json<{ error: string }>();
    throw new Error(`Location report rejected: ${error}`);
  }
}
```

---

## 3. Worker — Consent Check and Precision Reduction

```typescript
// workers/geo-privacy/src/index.ts
export interface Env {
  CONSENT_KV: KVNamespace;
  ORIGIN_URL: string; // downstream API
}

interface IncomingCoord {
  lat: number;
  lng: number;
  accuracy: number;
  timestamp: number;
}

// Truncate to 3 decimal places ≈ 111 m precision
function truncatePrecision(coord: IncomingCoord): { lat: number; lng: number; timestamp: number } {
  return {
    lat: Math.trunc(coord.lat * 1000) / 1000,
    lng: Math.trunc(coord.lng * 1000) / 1000,
    timestamp: coord.timestamp,
    // accuracy is dropped — not forwarded to origin
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const userId = request.headers.get("X-User-Id");
    if (!userId) {
      return Response.json({ error: "missing user id" }, { status: 400 });
    }

    // 1. Validate consent record
    const consentRecord = await env.CONSENT_KV.get(`consent:${userId}`, "json") as
      | { granted: boolean; version: string; ts: number }
      | null;

    if (!consentRecord?.granted) {
      return Response.json(
        { error: "no geolocation consent on record for this user" },
        { status: 403 }
      );
    }

    // 2. Parse and sanitise the payload
    let coord: IncomingCoord;
    try {
      coord = await request.json<IncomingCoord>();
    } catch {
      return Response.json({ error: "invalid JSON" }, { status: 400 });
    }

    const sanitised = truncatePrecision(coord);

    // 3. Forward sanitised payload — no raw coords ever leave the Worker
    const originRes = await fetch(env.ORIGIN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userId, ...sanitised }),
    });

    return new Response(originRes.body, {
      status: originRes.status,
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## 4. Worker — Consent Record Management Endpoint

```typescript
// workers/geo-privacy/src/consent.ts  (mount at /consent in the same Worker)
export async function handleConsent(
  request: Request,
  env: Env
): Promise<Response> {
  if (request.method !== "PUT") return new Response("Method not allowed", { status: 405 });

  const userId = request.headers.get("X-User-Id");
  if (!userId) return Response.json({ error: "missing user id" }, { status: 400 });

  const { granted, version } = await request.json<{ granted: boolean; version: string }>();

  await env.CONSENT_KV.put(
    `consent:${userId}`,
    JSON.stringify({ granted, version, ts: Date.now() }),
    { expirationTtl: 60 * 60 * 24 * 365 } // 1 year
  );

  return Response.json({ ok: true });
}
```

---

## 5. wrangler.toml

```toml
name = "geo-privacy"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[kv_namespaces]]
binding = "CONSENT_KV"
id = "your-kv-namespace-id"

[vars]
ORIGIN_URL = "https://api.example.com/location"
```

---

## Anti-Patterns

- **Forwarding raw accuracy values to origin.** Accuracy in metres is a fingerprinting vector — it reveals device hardware class. Drop it at the Worker, never forward it.
- **Storing consent in the mobile app only.** The device can be spoofed; consent records must live server-side in KV so the API boundary can enforce them regardless of client state.
- **Using 6-decimal precision on the server "just in case".** Six decimals (±0.1 m) is surveillance-grade. Truncate to 3 (±111 m) or fewer for most use-cases; only keep high precision for navigation features that explicitly need it.
- **Passing coordinates in URL query parameters.** Query strings end up in server access logs. Always POST coordinates in the request body.

---

## Gotchas

- **`Math.round` vs `Math.trunc` for truncation.** `Math.round(51.5005 * 1000) / 1000` = `51.501`, which is rounding up and leaking sub-precision. Use `Math.trunc` to strictly floor toward zero.
- **Capacitor Geolocation on Android 12+ requires `ACCESS_COARSE_LOCATION` for approximate mode.** Requesting only coarse on the device reduces what the app can capture before the Worker even sees it.
- **KV consistency.** KV reads are eventually consistent across regions. A consent revocation written in one region may take up to 60 seconds to propagate. For immediate revocation, use a Durable Object or D1 instead of KV.
- **iOS background location.** Capturing location in the background requires `NSLocationAlwaysAndWhenInUseUsageDescription` and `Always` permission — subject to additional App Store review scrutiny.

---

## Verification

```bash
# 1. Write a consent record
curl -X PUT "https://geo-privacy.example.workers.dev/consent" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user_001" \
  -d '{"granted":true,"version":"1.0"}'

# 2. Post a coordinate — should succeed with truncated lat/lng forwarded
curl -X POST "https://geo-privacy.example.workers.dev/location" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user_001" \
  -d '{"lat":51.500729,"lng":-0.124625,"accuracy":15,"timestamp":1724400000000}'

# 3. Revoke consent then retry — should return 403
curl -X PUT "https://geo-privacy.example.workers.dev/consent" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: user_001" \
  -d '{"granted":false,"version":"1.0"}'

curl -X POST "https://geo-privacy.example.workers.dev/location" \
  -H "X-User-Id: user_001" \
  -H "Content-Type: application/json" \
  -d '{"lat":51.500729,"lng":-0.124625,"accuracy":15,"timestamp":1724400000001}'
# Expected: 403 {"error":"no geolocation consent on record for this user"}
```

---

## Related

- `capacitor-d1-sqlite-offline-sync.md`
- `capacitor-http-plugin-workers-cors.md`
- `mobile-location-geofencing-background.md`
- `mobile-gdpr-mobile.md`
- `capacitor-native-bridge-plugin-development.md`

---

## Sources

- `@capacitor/geolocation` — https://capacitorjs.com/docs/apis/geolocation
- Cloudflare KV — https://developers.cloudflare.com/kv/
- GDPR Article 4(1) definition of personal data — https://gdpr-info.eu/art-4-gdpr/
- CCPA "precise geolocation" definition — https://oag.ca.gov/privacy/ccpa
- Cloudflare Workers — https://developers.cloudflare.com/workers/
