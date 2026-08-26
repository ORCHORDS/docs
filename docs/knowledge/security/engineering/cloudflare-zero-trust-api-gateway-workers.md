# Cloudflare Zero Trust as an API Gateway Protecting Internal Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have internal Cloudflare Workers exposed on `api.internal.yourdomain.com` that must not be reachable by arbitrary internet clients. You need every request to be authenticated and auditable, with machine-to-machine auth for Worker-to-Worker calls.

## Context

Cloudflare Zero Trust (formerly Cloudflare Access) can front any Workers route and enforce identity-based policies before a request reaches the Worker. For service-to-service calls, Access issues **service tokens** (`CF-Access-Client-Id` / `CF-Access-Client-Secret`). The upstream Access layer validates these and forwards a signed JWT (`Cf-Access-Jwt-Assertion`). The downstream Worker verifies this JWT using the Access JWKS endpoint and extracts claims for audit logging into D1.

---

## Zero Trust Application Setup (Terraform)

```hcl
# infra/zero-trust.tf
resource "cloudflare_zero_trust_access_application" "internal_api" {
  zone_id          = var.zone_id
  name             = "Internal API Gateway"
  domain           = "api.internal.${var.domain}"
  type             = "self_hosted"
  session_duration = "1h"

  # Require either a service token or a valid IdP session
  auto_redirect_to_identity = false
}

resource "cloudflare_zero_trust_access_policy" "service_tokens" {
  application_id = cloudflare_zero_trust_access_application.internal_api.id
  zone_id        = var.zone_id
  name           = "Service Tokens"
  precedence     = 1
  decision       = "allow"

  include {
    service_token = [cloudflare_zero_trust_access_service_token.worker_caller.id]
  }
}

resource "cloudflare_zero_trust_access_service_token" "worker_caller" {
  zone_id = var.zone_id
  name    = "caller-worker"
  # Outputs: client_id, client_secret — store as wrangler secrets
}
```

---

## Calling Worker — Attaching Service Token Headers

```typescript
// caller-worker/index.ts
// Each Worker that calls api.internal.yourdomain.com has its own service token.

interface Env {
  CF_ACCESS_CLIENT_ID: string;      // wrangler secret
  CF_ACCESS_CLIENT_SECRET: string;  // wrangler secret
  INTERNAL_API_URL: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const apiResponse = await fetch(`${env.INTERNAL_API_URL}/v1/data`, {
      method: 'GET',
      headers: {
        'CF-Access-Client-Id': env.CF_ACCESS_CLIENT_ID,
        'CF-Access-Client-Secret': env.CF_ACCESS_CLIENT_SECRET,
        'Content-Type': 'application/json',
      },
    });

    if (!apiResponse.ok) {
      return new Response(`Upstream error: ${apiResponse.status}`, { status: 502 });
    }

    return apiResponse;
  },
};
```

---

## Downstream Worker — JWT Verification and Audit Logging

```typescript
// internal-api-worker/index.ts
interface Env {
  CF_ACCESS_TEAM_DOMAIN: string;  // e.g. "myteam.cloudflareaccess.com"
  DB: D1Database;
}

interface AccessJwtPayload {
  aud: string[];
  email: string;
  sub: string;       // service token client_id or user identity
  iat: number;
  exp: number;
  type: string;      // 'app' for service tokens, 'user' otherwise
  common_name?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const jwtToken = request.headers.get('Cf-Access-Jwt-Assertion');
    if (!jwtToken) return new Response('Missing Access JWT', { status: 401 });

    let payload: AccessJwtPayload;
    try {
      payload = await verifyAccessJwt(jwtToken, env.CF_ACCESS_TEAM_DOMAIN);
    } catch (e) {
      return new Response('Invalid Access JWT', { status: 401 });
    }

    // Audit log to D1
    await env.DB
      .prepare(`
        INSERT INTO access_audit_log (sub, email, type, ray_id, requested_at)
        VALUES (?, ?, ?, ?, ?)
      `)
      .bind(
        payload.sub,
        payload.email ?? '',
        payload.type,
        request.headers.get('CF-Ray') ?? '',
        Math.floor(Date.now() / 1000),
      )
      .run();

    return Response.json({ data: 'protected resource', caller: payload.sub });
  },
};

async function verifyAccessJwt(
  token: string,
  teamDomain: string,
): Promise<AccessJwtPayload> {
  const certsUrl = `https://${teamDomain}/cdn-cgi/access/certs`;
  const certsResponse = await fetch(certsUrl);
  if (!certsResponse.ok) throw new Error('Failed to fetch Access JWKS');
  const { keys } = await certsResponse.json<{ keys: JsonWebKey[] }>();

  // Parse the JWT header to find the correct kid
  const [headerB64, payloadB64, sigB64] = token.split('.');
  const header = JSON.parse(atob(headerB64)) as { alg: string; kid: string };
  const jwk = keys.find((k: any) => k.kid === header.kid);
  if (!jwk) throw new Error(`No key found for kid ${header.kid}`);

  const key = await crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify'],
  );

  const signingInput = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const signature = Uint8Array.from(atob(sigB64.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
  const valid = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, signature, signingInput);
  if (!valid) throw new Error('JWT signature invalid');

  const payload = JSON.parse(atob(payloadB64)) as AccessJwtPayload;
  if (payload.exp < Math.floor(Date.now() / 1000)) throw new Error('JWT expired');
  return payload;
}
```

---

## D1 Audit Log Schema

```sql
-- audit-schema.sql
CREATE TABLE IF NOT EXISTS access_audit_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  sub           TEXT    NOT NULL,
  email         TEXT    NOT NULL,
  type          TEXT    NOT NULL,
  ray_id        TEXT    NOT NULL,
  requested_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_sub ON access_audit_log(sub);
CREATE INDEX IF NOT EXISTS idx_audit_requested_at ON access_audit_log(requested_at);
```

---

## Mutual Service-to-Service Auth Pattern

Each internal Worker has its own service token. The downstream Worker can inspect `payload.sub` (the service token's `client_id`) and enforce caller-specific authorization rules:

```typescript
const ALLOWED_CALLERS: Record<string, string[]> = {
  'billing-worker-client-id': ['/v1/invoices', '/v1/payments'],
  'reporting-worker-client-id': ['/v1/reports'],
};

function authorizeCallerPath(sub: string, pathname: string): boolean {
  const allowed = ALLOWED_CALLERS[sub] ?? [];
  return allowed.some(prefix => pathname.startsWith(prefix));
}
```

---

## Anti-patterns

- **Trusting `Cf-Access-Jwt-Assertion` without signature verification** — the header can be forged; always verify the signature against the team's JWKS.
- **Caching the JWKS response for too long** — Access rotates keys; cache with a short TTL (max 5 minutes) or re-fetch on verification failure.
- **Sharing one service token across all caller Workers** — per-Worker tokens enable per-caller revocation and audit trails.
- **Exposing the `CF-Access-Client-Secret` in logs** — it is equivalent to a password.

## Gotchas

- The JWKS endpoint (`/cdn-cgi/access/certs`) returns EC or RSA keys depending on your Access configuration; ensure the `importKey` algorithm matches.
- `Cf-Access-Jwt-Assertion` is forwarded by Access only after successful authentication; if the header is missing, the request bypassed Access (e.g. called via a direct Workers route without the Access policy attached).
- D1 writes are non-blocking with `.run()` but errors are silently swallowed unless you `await` and check `result.success`.

## Verification

```bash
# Request without service token — Access should return 403 before reaching the Worker
curl -i https://api.internal.yourdomain.com/v1/data
# HTTP/2 403

# Request with valid service token
curl -i https://api.internal.yourdomain.com/v1/data \
  -H 'CF-Access-Client-Id: <client-id>' \
  -H 'CF-Access-Client-Secret: <client-secret>'
# HTTP/2 200  {"data":"protected resource"}
```

## Related

- `workers-request-signing-hmac-sha256-verification.md`
- `workers-oauth2-client-credentials-d1-token-cache.md`
- Cloudflare Zero Trust service tokens documentation

## Sources

- https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/
- https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
