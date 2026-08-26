# Cloudflare Access JWT Validation in Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You protect a Worker (or an origin behind a Worker) with Cloudflare Access. Once a user authenticates,
Access injects `Cf-Access-Jwt-Assertion` and `Cf-Access-Authenticated-User-Email` headers into every
request. You need to:
1. Verify the JWT is genuine (signed by your team's Access cert) and not spoofed.
2. Extract the identity payload (sub, email, groups, custom claims) for authorization logic.
3. Propagate identity to downstream D1 queries or service-to-service Workers calls.

Skipping JWT validation means any request with a forged header bypasses Access entirely.

## Context

Cloudflare Access issues JWTs signed with RS256 (RSA-SHA256). The public keys are published at:
`https://<your-team>.cloudflareaccess.com/cdn-cgi/access/certs`

Each JWT payload contains:
- `iss`: `https://<your-team>.cloudflareaccess.com`
- `aud`: the Access Application's client ID (array)
- `sub`: the user's identity UUID
- `email`: the authenticated email
- `groups`: Access group memberships
- `iat` / `exp`: standard claims
- `custom`: custom OIDC claims if configured

The Workers runtime exposes the Web Crypto API, so RS256 verification is fully native — no external
libraries are required in production. For local dev, use `jose` or `@tsndr/cloudflare-worker-jwt`.

## JWT Validation Utility

```typescript
// src/lib/access-jwt.ts
export interface AccessJWTPayload {
  iss: string;
  aud: string[];
  sub: string;
  email: string;
  groups?: string[];
  custom?: Record<string, unknown>;
  iat: number;
  exp: number;
  nonce?: string;
}

export interface AccessJWTConfig {
  teamDomain:    string;   // e.g. "orchords.cloudflareaccess.com"
  audienceTag:   string;   // Access Application Client ID (AUD)
  clockSkewSec?: number;   // tolerated clock drift, default 30
}

type JWK = { kid: string; kty: string; n: string; e: string; alg: string; use: string };
type JWKS = { keys: JWK[] };

// Module-level JWKS cache (survives across requests in one isolate)
const jwksCache = new Map<string, { keys: CryptoKey[]; fetchedAt: number }>();
const JWKS_CACHE_TTL_SEC = 600;  // 10 minutes

async function fetchPublicKeys(teamDomain: string): Promise<CryptoKey[]> {
  const cached = jwksCache.get(teamDomain);
  if (cached && (Date.now() / 1000 - cached.fetchedAt) < JWKS_CACHE_TTL_SEC) {
    return cached.keys;
  }

  const resp = await fetch(`https://${teamDomain}/cdn-cgi/access/certs`);
  if (!resp.ok) throw new Error(`JWKS fetch failed: ${resp.status}`);

  const jwks: JWKS = await resp.json();
  const keys = await Promise.all(
    jwks.keys
      .filter((k) => k.kty === "RSA" && k.use === "sig")
      .map((k) =>
        crypto.subtle.importKey(
          "jwk",
          k,
          { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
          false,
          ["verify"],
        ),
      ),
  );

  jwksCache.set(teamDomain, { keys, fetchedAt: Date.now() / 1000 });
  return keys;
}

function base64UrlDecode(s: string): Uint8Array {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

export async function verifyAccessJWT(
  token: string,
  cfg: AccessJWTConfig,
): Promise<AccessJWTPayload> {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("malformed JWT");

  const [headerB64, payloadB64, sigB64] = parts;
  const header  = JSON.parse(atob(headerB64.replace(/-/g, "+").replace(/_/g, "/")));
  const payload = JSON.parse(new TextDecoder().decode(base64UrlDecode(payloadB64))) as AccessJWTPayload;
  const signingInput = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const signature    = base64UrlDecode(sigB64);

  if (header.alg !== "RS256") throw new Error(`unexpected algorithm: ${header.alg}`);

  const keys    = await fetchPublicKeys(cfg.teamDomain);
  const skewSec = cfg.clockSkewSec ?? 30;
  const now     = Math.floor(Date.now() / 1000);

  // Verify signature against any current key (key rotation tolerant)
  let sigValid = false;
  for (const key of keys) {
    if (await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, signature, signingInput)) {
      sigValid = true;
      break;
    }
  }
  if (!sigValid) throw new Error("JWT signature verification failed");

  // Validate standard claims
  if (payload.iss !== `https://${cfg.teamDomain}`) {
    throw new Error(`unexpected issuer: ${payload.iss}`);
  }
  if (!payload.aud.includes(cfg.audienceTag)) {
    throw new Error(`audience mismatch: ${payload.aud.join(", ")}`);
  }
  if (payload.exp < now - skewSec) {
    throw new Error("JWT has expired");
  }
  if (payload.iat > now + skewSec) {
    throw new Error("JWT issued in the future");
  }

  return payload;
}
```

## Worker Middleware: Access Guard

```typescript
// src/middleware/access-guard.ts
import { verifyAccessJWT, type AccessJWTPayload, type AccessJWTConfig } from "../lib/access-jwt";

export interface RequestWithIdentity extends Request {
  identity: AccessJWTPayload;
}

export function accessGuard(cfg: AccessJWTConfig) {
  return async (req: Request): Promise<{ identity: AccessJWTPayload } | Response> => {
    const token =
      req.headers.get("Cf-Access-Jwt-Assertion") ??
      req.headers.get("Authorization")?.replace(/^Bearer\s+/i, "");

    if (!token) {
      return new Response(JSON.stringify({ error: "missing access token" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }

    try {
      const identity = await verifyAccessJWT(token, cfg);
      return { identity };
    } catch (err) {
      return new Response(JSON.stringify({ error: String(err) }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    }
  };
}

// Usage in main Worker:
export interface Env {
  CLOUDFLARE_TEAM_DOMAIN: string;
  ACCESS_AUD_TAG: string;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const cfg = {
      teamDomain:  env.CLOUDFLARE_TEAM_DOMAIN,
      audienceTag: env.ACCESS_AUD_TAG,
    };
    const guard = accessGuard(cfg);
    const result = await guard(req);

    if (result instanceof Response) return result;  // auth error

    const { identity } = result;
    // identity.email, identity.groups, identity.sub available here
    return new Response(JSON.stringify({ user: identity.email, groups: identity.groups }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Group-Based Authorization

```typescript
// src/lib/authz.ts
import type { AccessJWTPayload } from "./access-jwt";

export const GROUPS = {
  ADMIN:  "orchords-admins",
  OPS:    "orchords-ops",
  VIEWER: "orchords-viewers",
} as const;

export function requireGroup(identity: AccessJWTPayload, group: string): void {
  if (!identity.groups?.includes(group)) {
    throw Object.assign(new Error(`forbidden: requires group ${group}`), { status: 403 });
  }
}

export function hasGroup(identity: AccessJWTPayload, group: string): boolean {
  return identity.groups?.includes(group) ?? false;
}

// Row-level security: bind identity to D1 queries
export async function queryUserScoped(
  db: D1Database,
  identity: AccessJWTPayload,
  orgId: string,
): Promise<D1Result> {
  return db
    .prepare("SELECT * FROM events WHERE org_id = ? AND created_by = ?")
    .bind(orgId, identity.sub)
    .all();
}
```

## Terraform: Secrets for Team Domain and AUD

```hcl
# terraform/cloudflare-workers-access-secrets.tf
resource "cloudflare_workers_secret" "team_domain" {
  account_id  = var.cloudflare_account_id
  script_name = var.worker_script_name
  name        = "CLOUDFLARE_TEAM_DOMAIN"
  text        = var.cloudflare_team_domain   # e.g. "orchords.cloudflareaccess.com"
}

resource "cloudflare_workers_secret" "access_aud_tag" {
  account_id  = var.cloudflare_account_id
  script_name = var.worker_script_name
  name        = "ACCESS_AUD_TAG"
  text        = var.access_application_client_id
}
```

## Anti-patterns

- **Trusting `Cf-Access-Authenticated-User-Email` without verifying the JWT**: this header can be
  spoofed by any caller who bypasses Access. Always verify the JWT signature first.
- **Fetching JWKS on every request**: public keys are stable for days; fetch once and cache in
  module scope with a short TTL to handle key rotation.
- **Hardcoding the AUD tag in source**: the client ID is not a secret but is environment-specific;
  store it as a Worker secret or binding variable so staging and production use different apps.
- **Ignoring `exp` clock skew**: distributed systems have ±30 s clock drift; reject tokens without
  a small tolerance and you will get spurious 403s.

## Gotchas

- Cloudflare Access strips the JWT headers when forwarding to a public origin — the Worker receives
  them, but the origin behind the Worker does not unless you forward them manually.
- `crypto.subtle` is available in the Workers runtime globally; do not import polyfills.
- Access JWTs are short-lived (default 1 hour); do not cache the entire verified payload beyond the
  request — only cache the JWKS public keys.
- Service tokens (machine-to-machine) use the same JWT format but `email` is of the form
  `<service-token-id>@access` — check for this in identity-display logic.

## Verification

```bash
# Decode a JWT from an Access-protected request (no verification, inspection only)
TOKEN=$(curl -s -H "Cf-Access-Client-Id: $CF_CLIENT_ID" \
             -H "Cf-Access-Client-Secret: $CF_CLIENT_SECRET" \
             https://api.internal.example.com/ \
             -D - -o /dev/null | grep -i cf-access-jwt | awk '{print $2}')

# Decode payload (base64url decode the second segment)
echo "$TOKEN" | cut -d. -f2 | tr '_-' '/+' | base64 -d 2>/dev/null | jq .

# Fetch and inspect the JWKS endpoint
curl -s "https://orchords.cloudflareaccess.com/cdn-cgi/access/certs" | jq '.keys | length'
```

## Related

- `cloudflare-access-self-service-app-provisioning.md` — Access application setup
- `terraform-cloudflare-access-application-policy.md` — Terraform Access policies
- `cloudflare-zero-trust-staging-prod-isolation.md` — environment isolation
- `workers-secrets-rotation-automation.md` — rotating the AUD secret
- `cloudflare-workers-api-token-scoping.md` — API token vs service token patterns

## Sources

- https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://www.rfc-editor.org/rfc/rfc7517  (JWK specification)
