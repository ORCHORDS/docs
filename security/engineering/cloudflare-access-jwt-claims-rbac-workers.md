# Cloudflare Access JWT Claims for RBAC in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project's admin panel is protected by Cloudflare Access, but simply being "behind Access" is not enough — a junior moderator should not reach the same endpoints as a super-admin. Workers need to extract the Access JWT, verify it, and derive a role from custom claims or group membership before authorising each operation. Without this, any user who passes the Access identity checkpoint gains full admin capability.

## Context

Cloudflare Access injects a signed JWT into every request via the `Cf-Access-Jwt-Assertion` header. The JWT contains standard OIDC claims (`sub`, `email`, `aud`) plus any custom SAML attribute statements or IdP group memberships added via Access policies. Workers can verify this token using Cloudflare's public JWKS endpoint without an external network call when the certs are cached in KV.

## Threat Model

Attackers may attempt to:
- **Forge the JWT** — the signature check with Cloudflare's JWKS prevents this.
- **Reuse an expired JWT** — `exp` claim validation prevents this.
- **Escalate privileges** — a valid but low-privilege JWT should be blocked from admin endpoints.
- **Strip the header** — if the Worker is reachable directly (not through Access), the header is absent; the Worker must treat absent JWTs as unauthenticated.

```typescript
// rbac-threat-model.ts
type Risk = "jwt_forgery" | "expired_reuse" | "privilege_escalation" | "header_strip";

const controls: Record<Risk, string> = {
  jwt_forgery:          "RS256 signature verified against Cloudflare JWKS",
  expired_reuse:        "exp + iat claims checked against Date.now()",
  privilege_escalation: "Role derived from groups claim; endpoint requires minimum role",
  header_strip:         "Missing header returns 401 before any business logic",
};
```

## JWT Verification

Verify the `Cf-Access-Jwt-Assertion` header against Cloudflare's public JWKS. Cache the JWKS in KV with a 5-minute TTL to avoid per-request egress.

```typescript
// access-jwt.ts
export interface AccessClaims {
  sub: string;
  email: string;
  aud: string[];
  iss: string;
  iat: number;
  exp: number;
  custom: {
    groups?: string[];
    role?: string;
  };
}

const JWKS_URL = "https://<team>.cloudflareaccess.com/cdn-cgi/access/certs";
const CLOCK_LEEWAY_S = 30;

async function fetchJwks(kv: KVNamespace): Promise<JsonWebKeySet> {
  const cached = await kv.get("cf_access_jwks", "json");
  if (cached) return cached as JsonWebKeySet;

  const res = await fetch(JWKS_URL);
  const jwks = await res.json() as JsonWebKeySet;
  await kv.put("cf_access_jwks", JSON.stringify(jwks), { expirationTtl: 300 });
  return jwks;
}

function base64url(b64: string): Uint8Array {
  const padded = b64.replace(/-/g, "+").replace(/_/g, "/")
    .padEnd(b64.length + (4 - b64.length % 4) % 4, "=");
  return Uint8Array.from(atob(padded), c => c.charCodeAt(0));
}

async function importRsaPublicKey(jwk: JsonWebKey): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"]
  );
}

export async function verifyAccessJwt(
  token: string,
  audience: string,
  kv: KVNamespace
): Promise<AccessClaims> {
  const [headerB64, payloadB64, sigB64] = token.split(".");
  if (!headerB64 || !payloadB64 || !sigB64) throw new Error("malformed_jwt");

  const claims = JSON.parse(new TextDecoder().decode(base64url(payloadB64))) as AccessClaims;
  const now = Math.floor(Date.now() / 1000);

  if (claims.exp < now - CLOCK_LEEWAY_S) throw new Error("jwt_expired");
  if (!claims.aud.includes(audience)) throw new Error("jwt_audience_mismatch");

  const header = JSON.parse(new TextDecoder().decode(base64url(headerB64)));
  const jwks = await fetchJwks(kv);
  const jwk = (jwks as any).keys.find((k: any) => k.kid === header.kid);
  if (!jwk) throw new Error("unknown_kid");

  const pubKey = await importRsaPublicKey(jwk);
  const signingInput = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    pubKey,
    base64url(sigB64),
    signingInput
  );
  if (!valid) throw new Error("jwt_signature_invalid");

  return claims;
}
```

## RBAC Role Derivation

Map IdP groups or a custom `role` claim to internal example project roles. The role hierarchy is enforced here, not in the IdP.

```typescript
// rbac.ts
export type WaspRole = "viewer" | "moderator" | "admin" | "super_admin";

const GROUP_ROLE_MAP: Record<string, WaspRole> = {
  "example project-admins":       "admin",
  "example project-super-admins": "super_admin",
  "example project-moderators":   "moderator",
};

const ROLE_RANK: Record<WaspRole, number> = {
  viewer:      0,
  moderator:   1,
  admin:       2,
  super_admin: 3,
};

export function deriveRole(claims: AccessClaims): WaspRole {
  // Prefer explicit role claim; fall back to highest-ranked group membership
  if (claims.custom?.role && claims.custom.role in ROLE_RANK) {
    return claims.custom.role as WaspRole;
  }
  const groups = claims.custom?.groups ?? [];
  let highest: WaspRole = "viewer";
  for (const group of groups) {
    const mapped = GROUP_ROLE_MAP[group];
    if (mapped && ROLE_RANK[mapped] > ROLE_RANK[highest]) {
      highest = mapped;
    }
  }
  return highest;
}

export function requireRole(
  actual: WaspRole,
  minimum: WaspRole
): void {
  if (ROLE_RANK[actual] < ROLE_RANK[minimum]) {
    throw Object.assign(new Error("insufficient_role"), { status: 403 });
  }
}
```

## Hardening — Worker Middleware

Combine verification and role enforcement into a reusable middleware that populates request context with the caller's identity.

```typescript
// access-middleware.ts
export interface AuthContext {
  sub: string;
  email: string;
  role: WaspRole;
}

export async function withAccess(
  req: Request,
  env: { AUTH_KV: KVNamespace; CF_ACCESS_AUD: string },
  handler: (req: Request, auth: AuthContext) => Promise<Response>
): Promise<Response> {
  const token = req.headers.get("Cf-Access-Jwt-Assertion");
  if (!token) {
    return new Response(JSON.stringify({ error: "missing_access_token" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  try {
    const claims = await verifyAccessJwt(token, env.CF_ACCESS_AUD, env.AUTH_KV);
    const role = deriveRole(claims);
    return handler(req, { sub: claims.sub, email: claims.email, role });
  } catch (err: any) {
    const status = err.status ?? 401;
    return new Response(JSON.stringify({ error: err.message }), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }
}

// Usage in a route handler
export async function handleDeleteUser(
  req: Request,
  env: Env,
  _ctx: ExecutionContext
): Promise<Response> {
  return withAccess(req, env, async (_req, auth) => {
    requireRole(auth.role, "admin");
    // … deletion logic
    return new Response(JSON.stringify({ deleted: true }));
  });
}
```

## Monitoring

Log role enforcement failures to detect privilege escalation attempts.

```typescript
// rbac-audit.ts
export async function auditRbacFailure(
  email: string,
  actualRole: WaspRole,
  requiredRole: WaspRole,
  path: string,
  ctx: ExecutionContext
): Promise<void> {
  ctx.waitUntil(
    fetch("https://logs.internal/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event: "rbac_denial",
        email,
        actual_role: actualRole,
        required_role: requiredRole,
        path,
        ts: Date.now(),
      }),
    })
  );
}
```

## Anti-patterns

- Trusting the `role` claim without a signature check — the JWT must be verified first.
- Hardcoding email addresses instead of group membership for role assignment.
- Checking audience as a substring match — use `Array.prototype.includes` for exact comparison.
- Caching the JWKS indefinitely — Cloudflare rotates keys; a stale cache causes 401 storms.
- Skipping the `exp` check because "Cloudflare already did it" — Workers are responsible for their own validation.

## Gotchas

- The `Cf-Access-Jwt-Assertion` header is set by Cloudflare's edge before the request reaches the Worker, but it is not automatically stripped from requests that bypass Access (direct Worker URL). The Worker must validate the signature regardless.
- Custom SAML attributes arrive under `custom` in the JWT only if the Access application is configured with an attribute statement mapping.
- KV `get` with `"json"` returns `null` when the key is missing — handle the null case before using the JWKS.
- The `kid` in the JWT header must match exactly; Cloudflare rotates keys and may serve multiple active kids at once.
- `super_admin` actions should require re-authentication (step-up) via `acr` claim where supported by the IdP.

## Verification

```bash
# 1. Obtain a valid Access JWT by visiting the protected URL in a browser
#    and extracting the Cf-Access-Jwt-Assertion cookie/header.

# 2. Decode it without verification
jwt_payload=$(echo "$JWT" | cut -d. -f2 | base64 -d 2>/dev/null | jq .)
echo "$jwt_payload" | jq '.custom.groups'

# 3. Call the Worker endpoint with the JWT
curl -H "Cf-Access-Jwt-Assertion: $JWT" https://admin.example.com/internal/delete-user

# 4. Tamper: change one byte in the signature segment; expect 401 with jwt_signature_invalid
# 5. Remove the header entirely; expect 401 with missing_access_token
```

## Related

- /documentation/categories/security/cloudflare-access-jwt-assertion-validation.md
- /documentation/categories/security/cloudflare-access-service-token-rotation-and-emergency-revocation.md
- /documentation/categories/security/jwt-rfc-8725-validation-profile.md
- /documentation/categories/security/oauth-jwt-access-token-profile-rfc9068.md
- /documentation/categories/security/zero-trust-device-posture-workers-enforcement.md

## Sources

- https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/worker-apps/
- https://www.rfc-editor.org/rfc/rfc8725 (JWT Best Current Practices)
- https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- https://developers.cloudflare.com/cloudflare-one/policies/access/
