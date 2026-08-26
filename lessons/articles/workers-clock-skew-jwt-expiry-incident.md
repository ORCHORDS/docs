# Workers Clock Skew JWT Expiry Incident

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
After a routine auth-service deployment, 3–8% of API requests from mobile clients began returning HTTP 401 "Token expired" even when the JWT had been issued seconds earlier and had a 15-minute lifetime. The errors were transient and self-resolved when clients retried, but only after the token issuer's clock drifted back into alignment.

## Context
Cloudflare Workers expose `Date.now()` and `new Date()` backed by the edge node's system clock. The Workers runtime does NOT synchronise with the token issuer's clock. When a JWT is issued by an external auth service (e.g., Auth0, Firebase Auth, or a self-hosted OIDC provider) and validated inside a Worker, any clock skew between the issuer and the validating edge node can cause valid tokens to appear expired. The Cloudflare edge colo validated `exp` (expiry) strictly against `Date.now()`, and the issuer's NTP had drifted +47 seconds relative to the colo's clock, making freshly-minted tokens appear 47 seconds stale.

---

## Root Cause: Strict `exp` Validation Without Clock Skew Tolerance

```typescript
// lib/jwt.ts — BUGGY (no clock skew tolerance)
import { importSPKI, jwtVerify, type JWTPayload } from "jose";

export async function verifyToken(token: string, publicKeyPem: string): Promise<JWTPayload> {
  const publicKey = await importSPKI(publicKeyPem, "RS256");

  // jwtVerify uses Date.now() internally for exp/nbf checks
  // No clockTolerance → 1-second skew can reject a brand-new token
  const { payload } = await jwtVerify(token, publicKey, {
    algorithms: ["RS256"],
    issuer: "https://auth.example.com",
    audience: "api.example.com",
  });

  return payload;
}
```

The `jose` library's `jwtVerify` defaults to zero clock tolerance. A 47-second issuer drift meant every token issued in the previous 47 seconds was rejected.

---

## Correct Pattern: Add Clock Skew Tolerance

```typescript
// lib/jwt.ts — FIXED
import { importSPKI, jwtVerify, type JWTPayload } from "jose";

// Allow up to 60 seconds of clock skew in either direction.
// This means a token that "expired" up to 60s ago is still accepted,
// and a token with nbf up to 60s in the future is still accepted.
const CLOCK_TOLERANCE_SECONDS = 60;

export async function verifyToken(
  token: string,
  publicKeyPem: string,
  audience: string,
): Promise<JWTPayload> {
  const publicKey = await importSPKI(publicKeyPem, "RS256");

  const { payload } = await jwtVerify(token, publicKey, {
    algorithms: ["RS256"],
    issuer: "https://auth.example.com",
    audience,
    clockTolerance: CLOCK_TOLERANCE_SECONDS,
  });

  return payload;
}
```

### Alternative: JWKS auto-fetch with built-in tolerance

If the issuer exposes a JWKS endpoint, use `createRemoteJWKSet` to avoid caching stale public keys and set tolerance at the same time:

```typescript
// lib/jwt-remote.ts
import { createRemoteJWKSet, jwtVerify, type JWTPayload } from "jose";

// Cache the JWKS fetcher at module scope — Workers module scope
// persists across requests on the same isolate
let jwks: ReturnType<typeof createRemoteJWKSet> | null = null;

function getJwks(jwksUri: string) {
  if (!jwks) {
    jwks = createRemoteJWKSet(new URL(jwksUri), {
      cacheMaxAge: 10 * 60 * 1000, // 10 min key cache
    });
  }
  return jwks;
}

export async function verifyTokenRemote(
  token: string,
  env: { JWKS_URI: string; JWT_AUDIENCE: string; JWT_ISSUER: string }
): Promise<JWTPayload> {
  const keySet = getJwks(env.JWKS_URI);

  const { payload } = await jwtVerify(token, keySet, {
    issuer: env.JWT_ISSUER,
    audience: env.JWT_AUDIENCE,
    clockTolerance: 60, // seconds
  });

  return payload;
}
```

---

## Monitoring: Emit Clock Skew as a Metric

Track the delta between `iat` (issued-at) and `Date.now()` on every verified token to surface drift before it causes failures:

```typescript
// lib/jwt-monitor.ts
export interface VerifyResult {
  payload: JWTPayload;
  clockSkewMs: number;
}

export async function verifyAndMeasure(
  token: string,
  env: Env,
): Promise<VerifyResult> {
  const now = Date.now();
  const payload = await verifyTokenRemote(token, env);

  const iat = (payload.iat ?? 0) * 1000; // convert seconds to ms
  const clockSkewMs = now - iat;          // positive = our clock is ahead of issuer

  // Write to Analytics Engine for alerting
  env.ANALYTICS.writeDataPoint({
    blobs: ["jwt_clock_skew"],
    doubles: [clockSkewMs],
    indexes: [env.SERVICE_NAME],
  });

  // Alert if skew exceeds half of token lifetime
  const exp = (payload.exp ?? 0) * 1000;
  const lifetimeMs = exp - iat;
  if (Math.abs(clockSkewMs) > lifetimeMs / 2) {
    console.error(`Clock skew ${clockSkewMs}ms exceeds 50% of token lifetime ${lifetimeMs}ms`);
  }

  return { payload, clockSkewMs };
}
```

---

## Wrangler Environment Bindings

```jsonc
// wrangler.jsonc
{
  "vars": {
    "JWKS_URI": "https://auth.example.com/.well-known/jwks.json",
    "JWT_ISSUER": "https://auth.example.com",
    "JWT_AUDIENCE": "api.example.com",
    "SERVICE_NAME": "api-gateway"
  },
  "analytics_engine_datasets": [
    { "binding": "ANALYTICS", "dataset": "jwt_metrics" }
  ]
}
```

---

## Anti-patterns
- Zero clock tolerance with short-lived tokens (< 5 minutes) — any NTP drift causes spurious rejections.
- Caching the JWKS response indefinitely in KV without a TTL — key rotation at the issuer becomes invisible to the Worker.
- Using `Math.floor(Date.now() / 1000)` to manually check `exp` without accounting for skew.
- Setting `clockTolerance` larger than the token lifetime — defeats the purpose of expiry.
- Not alerting on high `clockSkewMs` values before they cause failures; skew grows gradually and is detectable early.

## Gotchas
- `jose`'s `clockTolerance` is bidirectional: it relaxes both `exp` (future) and `nbf` (past) checks. A tolerance of 60s means a token with `nbf = now + 59s` is accepted — acceptable for skew mitigation but document this explicitly.
- Workers `Date.now()` may be frozen during CPU burst handling; it is not a high-resolution clock. Do not use it for sub-second timing.
- `createRemoteJWKSet` makes an outbound fetch to the JWKS endpoint — this counts against your Worker's subrequest budget (50 subrequests per request). Cache the result at module scope.
- Auth0 and similar providers use asymmetric keys by default; symmetric (HS256) tokens require the shared secret in a Worker secret, never a var.
- Token issuers with rolling key rotation may change kid (key ID) mid-flight; always match by `kid` first, then fall back to trying all keys.

## Verification

```bash
# Decode a JWT without verification to inspect iat/exp
echo "<TOKEN>" | cut -d. -f2 | base64 -d 2>/dev/null | jq '{iat, exp, iss, aud}'

# Compare issuer clock vs. local clock
curl -sI https://auth.example.com/ | grep -i date

# Replay a fresh token against your Worker
TOKEN=$(curl -s -X POST https://auth.example.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id":"...","client_secret":"...","grant_type":"client_credentials","audience":"api.example.com"}' \
  | jq -r .access_token)
curl -H "Authorization: Bearer $TOKEN" https://api.example.com/v1/healthz
```

```sql
-- Query Analytics Engine for clock skew distribution (last 1 hour)
SELECT
  AVG(_sample_interval * doubles[1]) as avg_skew_ms,
  MAX(doubles[1]) as max_skew_ms
FROM jwt_metrics
WHERE timestamp > NOW() - INTERVAL '1' HOUR
  AND blobs[1] = 'jwt_clock_skew';
```

## Related
- `cloudflare-access-service-token-rotation-outage.md`
- `certificate-expiry-outage.md`
- `leap-second-clock-sync-incidents.md`
- `workers-secrets-propagation-delay-auth-incident.md`
- `timezone-clock-bugs-bite-at-boundaries.md`

## Sources
- https://developers.cloudflare.com/workers/runtime-apis/web-standards/#time
- https://github.com/panva/jose/blob/main/docs/functions/jwt_verify.jwtVerify.md
- https://www.rfc-editor.org/rfc/rfc7519#section-4.1.4
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://auth0.com/docs/secure/tokens/access-tokens/validate-access-tokens
