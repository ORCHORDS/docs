# Zero Trust Device Posture Workers Enforcement

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your Cloudflare Access application protects an internal Worker endpoint, but a user with valid credentials is connecting from an unmanaged personal laptop—no disk encryption, outdated OS, no EDR agent. You need the Worker to reject requests from devices that fail your organisation's posture policy, not just validate the Access JWT for identity.

---

## Context

Cloudflare Zero Trust's device posture system collects signals from the WARP client, third-party MDM platforms (Intune, Jamf, Crowdstrike Falcon, SentinelOne), and the Gateway agent. Posture check results are embedded as claims inside the Cloudflare Access JWT under the `devicePosture` key. Workers can read these claims after validating the Access JWT to enforce granular, per-endpoint posture policies without a separate API call.

The flow is:
1. User authenticates through Cloudflare Access → Access issues a JWT.
2. The Access JWT is passed as the `Cf-Access-Jwt-Assertion` header on every request to the protected Worker.
3. The Worker validates the JWT signature (JWKS endpoint), then inspects `devicePosture` claims.
4. Requests from non-compliant devices are rejected before reaching business logic.

This approach is zero-RTT (no external calls during the hot path) once the JWKS keys are cached in KV.

---

## Validating the Access JWT

```typescript
// workers/src/access-jwt.ts
import type { Env } from "./types";

interface AccessJWTPayload {
  aud: string[];
  email: string;
  exp: number;
  iat: number;
  sub: string;
  devicePosture?: Record<string, DevicePostureResult>;
}

interface DevicePostureResult {
  id: string;
  type: string;
  success: boolean;
  rule_name?: string;
}

const CERTS_URL = "https://yourteam.cloudflareaccess.com/cdn-cgi/access/certs";
const CACHE_TTL_S = 3600; // refresh JWKS every hour

async function getPublicKeys(env: Env): Promise<JsonWebKey[]> {
  const cached = await env.KV_SECURITY.get("access:jwks", "json") as JsonWebKey[] | null;
  if (cached) return cached;

  const resp = await fetch(CERTS_URL);
  if (!resp.ok) throw new Error(`Failed to fetch Access JWKS: ${resp.status}`);

  const data = await resp.json<{ keys: JsonWebKey[] }>();
  await env.KV_SECURITY.put("access:jwks", JSON.stringify(data.keys), {
    expirationTtl: CACHE_TTL_S,
  });
  return data.keys;
}

export async function validateAccessJWT(
  request: Request,
  env: Env,
  audience: string
): Promise<AccessJWTPayload> {
  const token = request.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) throw new Response("Missing Access JWT", { status: 401 });

  const [headerB64, payloadB64, sigB64] = token.split(".");
  if (!headerB64 || !payloadB64 || !sigB64) {
    throw new Response("Malformed JWT", { status: 401 });
  }

  const payload = JSON.parse(atob(payloadB64)) as AccessJWTPayload;

  // Expiry check
  if (Date.now() / 1000 > payload.exp) {
    throw new Response("JWT expired", { status: 401 });
  }

  // Audience check
  if (!payload.aud.includes(audience)) {
    throw new Response("JWT audience mismatch", { status: 401 });
  }

  // Signature verification
  const keys = await getPublicKeys(env);
  const signingInput = `${headerB64}.${payloadB64}`;
  const sigBytes = Uint8Array.from(atob(sigB64.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));

  let verified = false;
  for (const jwk of keys) {
    try {
      const key = await crypto.subtle.importKey(
        "jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]
      );
      verified = await crypto.subtle.verify(
        "RSASSA-PKCS1-v1_5",
        key,
        sigBytes,
        new TextEncoder().encode(signingInput)
      );
      if (verified) break;
    } catch {
      // Try next key
    }
  }

  if (!verified) throw new Response("JWT signature invalid", { status: 401 });

  return payload;
}
```

---

## Enforcing Device Posture Claims

```typescript
// workers/src/posture-check.ts

interface PosturePolicy {
  requireDiskEncryption: boolean;
  requireEDR: boolean;
  requireOSVersion: boolean;
  allowedOSVersionMinimum?: string;
}

// Check IDs come from your Zero Trust dashboard → Settings → Device Posture
const POSTURE_CHECK_IDS: Record<string, string> = {
  diskEncryption: "posture-check-uuid-disk-enc",
  edrCrowdstrike: "posture-check-uuid-edr-cs",
  osVersion: "posture-check-uuid-os-ver",
};

export function enforceDevicePosture(
  devicePosture: Record<string, DevicePostureResult> | undefined,
  policy: PosturePolicy
): { allowed: boolean; reason?: string } {
  if (!devicePosture) {
    return { allowed: false, reason: "No device posture data in JWT — WARP client required" };
  }

  if (policy.requireDiskEncryption) {
    const check = devicePosture[POSTURE_CHECK_IDS.diskEncryption];
    if (!check?.success) {
      return { allowed: false, reason: "Device disk encryption check failed" };
    }
  }

  if (policy.requireEDR) {
    const check = devicePosture[POSTURE_CHECK_IDS.edrCrowdstrike];
    if (!check?.success) {
      return { allowed: false, reason: "Device EDR check failed (CrowdStrike not active)" };
    }
  }

  if (policy.requireOSVersion) {
    const check = devicePosture[POSTURE_CHECK_IDS.osVersion];
    if (!check?.success) {
      return { allowed: false, reason: "Device OS version below minimum requirement" };
    }
  }

  return { allowed: true };
}

interface DevicePostureResult {
  id: string;
  type: string;
  success: boolean;
}
```

---

## Wiring It Together in the Worker Handler

```typescript
// workers/src/index.ts
import { validateAccessJWT } from "./access-jwt";
import { enforceDevicePosture } from "./posture-check";

const AUDIENCE = "your-access-application-aud-tag";

const POSTURE_POLICY = {
  requireDiskEncryption: true,
  requireEDR: true,
  requireOSVersion: true,
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // 1. Validate the Cloudflare Access JWT
    let payload;
    try {
      payload = await validateAccessJWT(request, env, AUDIENCE);
    } catch (e) {
      if (e instanceof Response) return e;
      return new Response("Authentication error", { status: 401 });
    }

    // 2. Enforce device posture
    const { allowed, reason } = enforceDevicePosture(
      payload.devicePosture,
      POSTURE_POLICY
    );

    if (!allowed) {
      // Log posture failure for SIEM
      await env.SECURITY_LOG_QUEUE.send({
        event: "device_posture_blocked",
        email: payload.email,
        reason,
        timestamp: new Date().toISOString(),
        ray: request.headers.get("cf-ray"),
      });

      return new Response(
        JSON.stringify({ error: "Device does not meet security requirements", detail: reason }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      );
    }

    // 3. Continue to business logic
    return handleBusinessLogic(request, env, payload.email);
  },
};

async function handleBusinessLogic(
  request: Request,
  env: Env,
  email: string
): Promise<Response> {
  // Your protected application logic here
  return new Response(JSON.stringify({ ok: true, user: email }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

---

## Tiered Posture Policies per Route

Not every endpoint needs the same posture bar. A read-only dashboard route can be more permissive than an admin mutation route:

```typescript
// workers/src/route-policies.ts
interface RoutePolicy {
  pattern: URLPattern;
  posture: { requireDiskEncryption: boolean; requireEDR: boolean; requireOSVersion: boolean };
}

const ROUTE_POLICIES: RoutePolicy[] = [
  {
    pattern: new URLPattern({ pathname: "/admin/*" }),
    posture: { requireDiskEncryption: true, requireEDR: true, requireOSVersion: true },
  },
  {
    pattern: new URLPattern({ pathname: "/api/data/*" }),
    posture: { requireDiskEncryption: true, requireEDR: false, requireOSVersion: false },
  },
  {
    pattern: new URLPattern({ pathname: "/dashboard" }),
    posture: { requireDiskEncryption: false, requireEDR: false, requireOSVersion: false },
  },
];

export function getPolicyForRequest(request: Request) {
  for (const rp of ROUTE_POLICIES) {
    if (rp.pattern.test(request.url)) return rp.posture;
  }
  // Default: strictest policy
  return { requireDiskEncryption: true, requireEDR: true, requireOSVersion: true };
}
```

---

## Anti-patterns

- **Trusting device posture without verifying the JWT signature**: An attacker who forges the `Cf-Access-Jwt-Assertion` header can craft arbitrary `devicePosture` claims. Always verify the signature first.
- **Hard-coding JWKS keys**: Access rotates its signing keys; always fetch from the JWKS endpoint and cache in KV with TTL.
- **Blocking with no user-facing reason**: Return a human-readable error body explaining which posture check failed so help-desk teams can assist users.
- **Applying posture checks to unauthenticated endpoints**: Posture data is only meaningful when the identity JWT is also validated; do not check posture independently.
- **Ignoring the `exp` claim**: An expired Access JWT from a previously compliant device must be rejected even if the posture claims show `success: true`.

---

## Gotchas

- **`devicePosture` is only populated when WARP is running**: Browser-only Access sessions (no WARP client) will have no posture data; plan your fallback policy accordingly.
- **Check IDs are UUIDs assigned by Cloudflare**: They differ per account and per check definition; retrieve them from the API: `GET /accounts/{id}/devices/posture`.
- **Grace periods**: Some posture checks (e.g., last-seen timestamps) have a grace window; a check can report `success: true` even if the device last checked in 23 hours ago if the check allows 24-hour intervals.
- **Multiple WARP profiles**: Devices enrolled in multiple Zero Trust organisations will send posture for the active profile only.
- **JWKS cache invalidation**: If Cloudflare rotates keys, your cached JWKS will be stale until TTL expires. Use a short TTL (≤ 1 hour) or catch JWT signature failures and retry with a fresh JWKS fetch.

---

## Verification

```bash
# 1. List device posture checks to get check UUIDs
curl -s https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/devices/posture \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name, type}'

# 2. Decode the Access JWT to inspect devicePosture claims
echo "$ACCESS_JWT" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq '.devicePosture'

# 3. Simulate a non-compliant request (missing WARP header)
curl -si https://your-worker.example.com/admin/dashboard \
  -H "Cf-Access-Jwt-Assertion: $VALID_JWT_NO_POSTURE"
# Expect: 403 with "No device posture data"

# 4. Confirm compliant device passes
curl -si https://your-worker.example.com/admin/dashboard \
  -H "Cf-Access-Jwt-Assertion: $VALID_JWT_WITH_POSTURE"
# Expect: 200
```

---

## Related

- `cloudflare-access-jwt-assertion-validation.md`
- `client-certificate-mtls-workers-zero-trust.md`
- `zero-trust-network-architecture-ztna.md`
- `durable-objects-auth-patterns.md`
- `service-binding-zero-trust-workers.md`

---

## Sources

- Cloudflare Zero Trust device posture: https://developers.cloudflare.com/cloudflare-one/identity/devices/
- Cloudflare Access JWT validation: https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
- Device posture API: https://developers.cloudflare.com/api/resources/zero_trust/subresources/devices/subresources/posture/
- WARP client device posture rules: https://developers.cloudflare.com/cloudflare-one/identity/devices/warp-client-checks/
