# JWT Audience Claim Validation in Workers for Multi-Tenant Applications

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A token issued for tenant `acme.example.com` is replayed against `rival.example.com`
hosted on the same Worker. Because both routes share the same JWT signing key, a naive
`verify(token)` call accepts it — the `aud` claim is never checked.

## Context

RFC 7519 requires that the `aud` (audience) claim be validated: if the claim is present,
the verifier MUST reject the token unless the verifier identifies itself with one of the
listed values. In a multi-tenant Worker that serves hundreds of subdomains, the audience
must encode the tenant identity so that a token minted for one tenant cannot be cross-
played against another.

Combine audience validation with the `iss` (issuer) claim for defense-in-depth: `iss`
narrows to the identity provider, `aud` narrows to the specific tenant resource.

---

## Canonical audience format

```
aud: "https://<tenant-slug>.api.example.com"
```

Alternatively, use an array to cover multiple audience recipients:

```json
{
  "aud": ["https://acme.api.example.com", "https://api.example.com/acme"]
}
```

The Worker determines the expected audience from the incoming `Host` header or from a
tenant lookup in D1/KV — never from the token itself.

---

## Verifying a JWT with audience and issuer checks

```typescript
import { decodeJwt, jwtVerify, createRemoteJWKSet } from 'jose';  // or jose-cloudflare-workers

interface Env {
  JWKS_URL: string;    // e.g. "https://auth.example.com/.well-known/jwks.json"
  JWT_ISSUER: string;  // e.g. "https://auth.example.com"
}

export async function verifyTenantJwt(
  token: string,
  expectedAudience: string,
  env: Env,
): Promise<{ sub: string; tenantId: string; scopes: string[] }> {
  const JWKS = createRemoteJWKSet(new URL(env.JWKS_URL));

  const { payload } = await jwtVerify(token, JWKS, {
    issuer: env.JWT_ISSUER,
    audience: expectedAudience,   // jose rejects if aud claim doesn't include this value
    clockTolerance: 30,           // seconds; handles minor clock skew
    algorithms: ['RS256', 'ES256'],
  });

  if (typeof payload.sub !== 'string' || !payload.sub) {
    throw new Error('JWT missing sub claim');
  }

  const tenantId = payload['tenant_id'] as string | undefined;
  if (!tenantId) throw new Error('JWT missing tenant_id claim');

  const scopes = (payload['scope'] as string | undefined ?? '').split(' ').filter(Boolean);
  return { sub: payload.sub, tenantId, scopes };
}
```

---

## Deriving expected audience from the request

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const host = request.headers.get('Host') ?? '';
    // Derive expected audience directly from the Host header
    const expectedAudience = `https://${host}`;

    const authHeader = request.headers.get('Authorization') ?? '';
    if (!authHeader.startsWith('Bearer ')) {
      return new Response('Unauthorized', { status: 401 });
    }
    const token = authHeader.slice(7);

    let claims: Awaited<ReturnType<typeof verifyTenantJwt>>;
    try {
      claims = await verifyTenantJwt(token, expectedAudience, env);
    } catch (err) {
      // Do NOT expose the internal error to the caller
      return new Response('Unauthorized', { status: 401 });
    }

    // Cross-check tenant_id from token against the host-derived tenant slug
    const hostTenantSlug = host.split('.')[0];  // "acme" from "acme.api.example.com"
    if (claims.tenantId !== hostTenantSlug) {
      return new Response('Forbidden: tenant mismatch', { status: 403 });
    }

    return handleRequest(request, env, claims);
  },
};
```

The double-check (audience claim + host-derived tenant slug) means an attacker must
forge both the `aud` claim and the `tenant_id` claim for a cross-tenant replay to succeed.

---

## Handling multiple valid audiences (service-to-service)

When an internal service calls another with a token that must be accepted by several
Worker instances:

```typescript
export async function verifyServiceToken(
  token: string,
  env: Env & { SERVICE_AUDIENCE: string },
): Promise<{ sub: string }> {
  const JWKS = createRemoteJWKSet(new URL(env.JWKS_URL));

  // Pass an array of acceptable audiences; any match is sufficient
  const { payload } = await jwtVerify(token, JWKS, {
    issuer: env.JWT_ISSUER,
    audience: [env.SERVICE_AUDIENCE, `${env.SERVICE_AUDIENCE}/v2`],
    algorithms: ['ES256'],
  });

  return { sub: String(payload.sub) };
}
```

---

## Caching JWKS with a bounded TTL

`createRemoteJWKSet` from `jose` caches keys in memory for the isolate's lifetime.
In Workers (where isolates are recycled frequently) this is usually sufficient, but you
should also set an explicit refresh interval to handle key rotations:

```typescript
import { createRemoteJWKSet } from 'jose';

let jwksCache: ReturnType<typeof createRemoteJWKSet> | null = null;
let cacheBuiltAt = 0;
const JWKS_TTL_MS = 15 * 60 * 1000; // 15 minutes

function getJWKS(url: string): ReturnType<typeof createRemoteJWKSet> {
  if (!jwksCache || Date.now() - cacheBuiltAt > JWKS_TTL_MS) {
    jwksCache = createRemoteJWKSet(new URL(url), { cacheMaxAge: JWKS_TTL_MS });
    cacheBuiltAt = Date.now();
  }
  return jwksCache;
}
```

---

## Anti-patterns

- **Skipping `audience` in `jwtVerify` options**: the library may not validate `aud` by default; always pass the expected value explicitly.
- **Trusting `aud` from the token to determine the tenant**: the token can claim any audience; the verifier must know its own identity independently.
- **Accepting `alg: none` or omitting `algorithms` allow-list**: allows algorithm confusion attacks.
- **Reflecting the error message from the JWT library** in the HTTP response: reveals whether the token was expired, had a wrong audience, etc. — useful to attackers.

## Gotchas

- `jose` audience matching is strict: `"https://acme.api.example.com"` does NOT match `"acme.api.example.com"` (missing scheme). Be consistent with your IdP's token issuance format.
- If the IdP issues a single-element array `["https://acme.api.example.com"]` and your code passes a string, most libraries compare string-to-string and accept the match, but verify this in your version of `jose`.
- For Cloudflare Access tokens the `aud` claim is the Access Application Audience Tag (a UUID), not a URL — see `cloudflare-access-jwt-assertion-validation.md`.

## Verification

```bash
# Decode the aud claim of a token without verifying (for inspection only)
echo "<token>" | cut -d. -f2 | base64 -d 2>/dev/null | jq '.aud, .iss, .sub, .exp'
```

Confirm `aud` matches the expected audience for the tenant you are testing against.

## Related

- `cloudflare-access-jwt-assertion-validation.md`
- `cloudflare-access-jwt-claims-rbac-workers.md`
- `jwt-rfc-8725-validation-profile.md`
- `jwt-algorithm-confusion-attack.md`
- `multi-tenancy-isolation-workers-kv-d1.md`
- `oidc-jwt-workers-edge-verification.md`

## Sources

- RFC 7519 Section 4.1.3 — "aud" (Audience) Claim — https://datatracker.ietf.org/doc/html/rfc7519#section-4.1.3
- RFC 8725 JWT Best Current Practices — https://datatracker.ietf.org/doc/html/rfc8725
- jose library — https://github.com/panva/jose
- Cloudflare Workers runtime — https://developers.cloudflare.com/workers/
