# Cloudflare Access Application Bypass Prevention

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A Cloudflare Access-protected application can be bypassed if the origin server is reachable directly (not only through the Cloudflare proxy), if the Worker fails to re-validate the Access JWT on each request, or if Access policies are misconfigured to allow unintended identity providers or service tokens.

## Context
Cloudflare Access sits in front of an application as a Zero Trust identity gateway. Traffic from browsers hits Access at `*.cloudflareaccess.com`, receives a signed JWT (`CF-Access-Jwt-Assertion`), and is forwarded to the origin with that header. A Worker or origin that trusts the header without verifying the JWT signature, or an origin that accepts direct traffic bypassing Access, defeats the entire control.

---

## Section 1 — Validate the Access JWT on Every Request

The Worker or origin must cryptographically verify the `CF-Access-Jwt-Assertion` header on every request, not just check for its presence. Cloudflare publishes JWKS at a well-known endpoint per team domain.

```typescript
interface Env {
  CF_ACCESS_TEAM_DOMAIN: string; // e.g. "yourteam.cloudflareaccess.com"
  CF_ACCESS_AUD: string;         // Application Audience (AUD) tag from Access dashboard
}

interface AccessJwtPayload {
  aud: string[];
  email: string;
  iat: number;
  exp: number;
  sub: string;
  iss: string;
  type: string;
}

let cachedKeys: CryptoKey[] | null = null;
let cacheExpiry = 0;

async function getAccessPublicKeys(teamDomain: string): Promise<CryptoKey[]> {
  if (cachedKeys && Date.now() < cacheExpiry) return cachedKeys;

  const jwksUrl = `https://${teamDomain}/cdn-cgi/access/certs`;
  const res = await fetch(jwksUrl, { cf: { cacheTtl: 600 } });
  if (!res.ok) throw new Error(`JWKS fetch failed: ${res.status}`);

  const { keys } = (await res.json()) as { keys: JsonWebKey[] };
  cachedKeys = await Promise.all(
    keys.map(k =>
      crypto.subtle.importKey(
        'jwk',
        k,
        { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
        false,
        ['verify']
      )
    )
  );
  cacheExpiry = Date.now() + 5 * 60 * 1000; // 5 minutes
  return cachedKeys;
}

async function verifyAccessJWT(
  token: string,
  env: Env
): Promise<AccessJwtPayload> {
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('Malformed JWT');

  const [headerB64, payloadB64, sigB64] = parts;
  const signingInput = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const signature = Uint8Array.from(
    atob(sigB64.replace(/-/g, '+').replace(/_/g, '/')),
    c => c.charCodeAt(0)
  );

  const keys = await getAccessPublicKeys(env.CF_ACCESS_TEAM_DOMAIN);
  let valid = false;
  for (const key of keys) {
    if (await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, signature, signingInput)) {
      valid = true;
      break;
    }
  }
  if (!valid) throw new Error('JWT signature invalid');

  const payload: AccessJwtPayload = JSON.parse(
    atob(payloadB64.replace(/-/g, '+').replace(/_/g, '/'))
  );

  // Audience check
  if (!payload.aud.includes(env.CF_ACCESS_AUD)) {
    throw new Error('JWT audience mismatch');
  }

  // Expiry check
  if (Math.floor(Date.now() / 1000) > payload.exp) {
    throw new Error('JWT expired');
  }

  // Issuer check
  if (payload.iss !== `https://${env.CF_ACCESS_TEAM_DOMAIN}`) {
    throw new Error('JWT issuer mismatch');
  }

  return payload;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const token = request.headers.get('CF-Access-Jwt-Assertion');
    if (!token) {
      return new Response('Unauthorized: missing Access JWT', { status: 401 });
    }
    try {
      const payload = await verifyAccessJWT(token, env);
      // Attach verified identity to downstream request
      const upstreamRequest = new Request(request, {
        headers: Object.fromEntries([
          ...request.headers.entries(),
          ['X-Verified-Email', payload.email],
          ['X-Verified-Sub', payload.sub],
        ])
      });
      return fetch(upstreamRequest);
    } catch (err) {
      return new Response(`Forbidden: ${(err as Error).message}`, { status: 403 });
    }
  }
};
```

---

## Section 2 — Lock Down the Origin to Cloudflare IPs Only

If the origin is a server outside Cloudflare (not a Worker), it must only accept connections from Cloudflare's published IP ranges. This prevents direct-to-origin bypass.

```bash
# Fetch Cloudflare IPs (run during deploy, store as allowlist)
curl -s https://www.cloudflare.com/ips-v4 > /etc/nginx/cloudflare-ips.conf
curl -s https://www.cloudflare.com/ips-v6 >> /etc/nginx/cloudflare-ips.conf
```

```nginx
# nginx: block any non-Cloudflare source
geo $cloudflare_ip {
  default 0;
  include /etc/nginx/cloudflare-ips.conf; # each line: 103.21.244.0/22 1;
}

server {
  listen 443 ssl;
  if ($cloudflare_ip = 0) {
    return 403 "Direct access blocked";
  }
  # Also verify CF-Access-Jwt-Assertion via lua or app layer
}
```

For Workers-only stacks, origins are other Workers or D1/R2/KV—none of which are reachable directly, so IP allowlisting is not applicable but JWT validation in the Worker still applies.

---

## Section 3 — Audit Access Policies for Over-Broad Rules

Access bypass often comes from misconfigured policy rules—particularly `Everyone` rules, overly broad email domain matches, or stale service tokens with no expiry.

```typescript
// Automated policy audit via Cloudflare API
async function auditAccessPolicies(apiToken: string, accountId: string): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/access/apps`,
    { headers: { Authorization: `Bearer ${apiToken}` } }
  );
  const { result: apps } = await res.json() as { result: AccessApp[] };

  for (const app of apps) {
    const policiesRes = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}/access/apps/${app.id}/policies`,
      { headers: { Authorization: `Bearer ${apiToken}` } }
    );
    const { result: policies } = await policiesRes.json() as { result: AccessPolicy[] };

    for (const policy of policies) {
      for (const rule of policy.include ?? []) {
        if ('everyone' in rule) {
          console.warn(`RISK: App "${app.name}" policy "${policy.name}" allows Everyone`);
        }
        if ('email_domain' in rule && (rule as any).email_domain?.domain === '*') {
          console.warn(`RISK: Wildcard email domain in app "${app.name}"`);
        }
      }
    }
  }
}
```

---

## Anti-patterns

- Checking only for the presence of `CF-Access-Jwt-Assertion` without verifying its signature — a forged header passes this check.
- Caching JWKS keys indefinitely — Cloudflare rotates keys; stale keys will reject valid tokens after rotation.
- Using `email` claim from the JWT for authorization without also checking `type` — service token JWTs have `type: "app"` and no email.
- Setting Access policies to `Allow` with no `Include` rules, or with `Everyone` included alongside `Allow` — this defeats the control.
- Relying on Access to protect the Cloudflare Dashboard or API routes that use the same hostname — Access does not protect Cloudflare's own infrastructure endpoints.
- Not setting an `AUD` (audience) on the application — without it any Access JWT from your team can be replayed to any app.

---

## Gotchas

- The `CF-Access-Jwt-Assertion` header is stripped by Cloudflare before forwarding to origins in some configurations; verify in the Access application settings whether the header is forwarded.
- Service tokens (`CF-Access-Client-Id` / `CF-Access-Client-Secret`) bypass the JWT flow entirely; audit service tokens separately and enforce short TTLs.
- Access allows configuring "bypass" rules (policy action = Bypass) that skip authentication for specific IP ranges or paths. Audit these regularly—they are legitimate but often forgotten.
- When using Workers as origins behind Access, the Worker receives the JWT header; it must still verify it because an attacker who knows your Worker route can send a crafted header directly to `workers.dev`.
- The `exp` claim uses Unix epoch seconds, not milliseconds; comparing with `Date.now()` (milliseconds) without dividing by 1000 gives false expiry results.

---

## Verification

1. Remove the `CF-Access-Jwt-Assertion` header from a request to your Worker (using curl) and confirm a `401` response.
2. Send a request with a forged / expired JWT and confirm a `403` response.
3. Attempt to reach the origin server directly (bypassing Cloudflare) and confirm the connection is refused or returns `403`.
4. Review Access policy configuration in the Cloudflare dashboard under **Zero Trust → Access → Applications** and confirm no `Everyone` include rules exist on production apps.
5. Use the audit script above to scan all apps programmatically and pipe results to your SIEM.

---

## Related

- `cloudflare-access-jwt-assertion-validation.md`
- `cloudflare-access-jwt-claims-rbac-workers.md`
- `cloudflare-access-service-token-rotation-and-emergency-revocation.md`
- `zero-trust-device-posture-workers-enforcement.md`
- `service-binding-zero-trust-workers.md`

---

## Sources

- https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
- https://developers.cloudflare.com/cloudflare-one/policies/access/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/
- https://www.cloudflare.com/ips/
- https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
