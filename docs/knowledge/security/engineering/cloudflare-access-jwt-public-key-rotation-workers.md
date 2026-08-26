# Cloudflare Access JWT Public Key Rotation Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker sits behind Cloudflare Access. The Worker validates the
`Cf-Access-Jwt-Assertion` header on every request to confirm the user was authenticated
by Access before the Worker ran. However:

- Cloudflare rotates the JWT signing keys periodically; after rotation, cached public keys
  are stale and every verification fails with `signature verification failed`.
- The Worker hard-codes the public key JWK, so it breaks silently the moment Cloudflare
  publishes a new key.
- The Worker fetches the JWKS endpoint on every request, adding latency and a dependency
  on Cloudflare's JWKS host inside the request path.

This article shows how to cache the JWKS in KV with automatic refresh, verify the JWT
correctly, and handle key rotation without downtime.

---

## Context

Cloudflare Access issues RS256-signed JWTs. The public keys are published at:

```
https://<your-team-domain>.cloudflareaccess.com/cdn-cgi/access/certs
```

The response is a standard JWKS document (`{ keys: [...] }`). Each key has a `kid`
(key ID). The JWT header contains a `kid` identifying which key was used to sign it.
Cloudflare can add new keys before retiring old ones, so a short overlap window exists
during rotation.

The correct verification flow is:

1. Decode the JWT header to get the `kid`.
2. Find a matching key in the cached JWKS.
3. If no matching key found, re-fetch the JWKS and retry once (covers rotation).
4. Verify the signature and standard claims (`iss`, `aud`, `exp`).

---

## Environment and Bindings

```toml
# wrangler.toml
[[kv_namespaces]]
binding = "JWKS_CACHE"
id = "..."

[vars]
ACCESS_TEAM_DOMAIN = "yourteam.cloudflareaccess.com"
ACCESS_AUD = "your-application-audience-tag"
```

```typescript
// src/env.ts
export interface Env {
  JWKS_CACHE: KVNamespace;
  ACCESS_TEAM_DOMAIN: string;
  ACCESS_AUD: string;
}
```

---

## JWKS Cache Layer

```typescript
// src/jwks-cache.ts
import type { Env } from './env';

const CACHE_KEY = 'access-jwks';
const CACHE_TTL_SECONDS = 3600; // 1 hour; Cloudflare rotates keys with ≥24h notice

export interface JwkSet {
  keys: JsonWebKey[];
}

export async function getJwks(env: Env, forceRefresh = false): Promise<JwkSet> {
  if (!forceRefresh) {
    const cached = await env.JWKS_CACHE.get<JwkSet>(CACHE_KEY, 'json');
    if (cached) return cached;
  }

  const url = `https://${env.ACCESS_TEAM_DOMAIN}/cdn-cgi/access/certs`;
  const resp = await fetch(url, {
    cf: { cacheTtl: 300, cacheEverything: false }, // Cloudflare fetch cache as backup
  });

  if (!resp.ok) {
    throw new Error(`JWKS fetch failed: ${resp.status} ${resp.statusText}`);
  }

  const jwks = await resp.json<JwkSet>();

  if (!Array.isArray(jwks.keys) || jwks.keys.length === 0) {
    throw new Error('JWKS response contained no keys');
  }

  await env.JWKS_CACHE.put(CACHE_KEY, JSON.stringify(jwks), {
    expirationTtl: CACHE_TTL_SECONDS,
  });

  return jwks;
}

export async function findKeyByKid(
  env: Env,
  kid: string,
  allowRefresh = true,
): Promise<JsonWebKey> {
  let jwks = await getJwks(env);
  let key = jwks.keys.find(k => (k as any).kid === kid);

  if (!key && allowRefresh) {
    // Key not found — may have rotated; force a fresh fetch
    jwks = await getJwks(env, true);
    key = jwks.keys.find(k => (k as any).kid === kid);
  }

  if (!key) {
    throw new Error(`No JWK found for kid: ${kid}`);
  }

  return key;
}
```

---

## JWT Verification

```typescript
// src/access-auth.ts
import type { Env } from './env';
import { findKeyByKid } from './jwks-cache';

export interface AccessClaims {
  sub: string;
  email: string;
  name?: string;
  groups?: string[];
  aud: string[];
  iss: string;
  exp: number;
  iat: number;
}

function decodeJwtHeader(token: string): { alg: string; kid: string } {
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('Invalid JWT format');
  try {
    return JSON.parse(atob(parts[0].replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    throw new Error('Failed to decode JWT header');
  }
}

function decodeJwtPayload(token: string): Record<string, unknown> {
  const parts = token.split('.');
  try {
    return JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
  } catch {
    throw new Error('Failed to decode JWT payload');
  }
}

async function verifyRs256Signature(
  token: string,
  publicKey: CryptoKey,
): Promise<boolean> {
  const parts = token.split('.');
  const signingInput = `${parts[0]}.${parts[1]}`;
  const signature = Uint8Array.from(
    atob(parts[2].replace(/-/g, '+').replace(/_/g, '/')),
    c => c.charCodeAt(0),
  );

  return crypto.subtle.verify(
    { name: 'RSASSA-PKCS1-v1_5' },
    publicKey,
    signature,
    new TextEncoder().encode(signingInput),
  );
}

export async function verifyAccessJwt(
  env: Env,
  token: string,
): Promise<AccessClaims> {
  const header = decodeJwtHeader(token);

  if (header.alg !== 'RS256') {
    throw new Error(`Unexpected algorithm: ${header.alg}`);
  }
  if (!header.kid) {
    throw new Error('JWT header missing kid');
  }

  // Fetch the correct public key (with one rotation-retry)
  const jwk = await findKeyByKid(env, header.kid);

  const publicKey = await crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['verify'],
  );

  const valid = await verifyRs256Signature(token, publicKey);
  if (!valid) {
    throw new Error('JWT signature verification failed');
  }

  const payload = decodeJwtPayload(token) as AccessClaims;
  const nowSec = Math.floor(Date.now() / 1000);

  // Validate standard claims
  if (!Array.isArray(payload.aud) || !payload.aud.includes(env.ACCESS_AUD)) {
    throw new Error('JWT audience mismatch');
  }

  const expectedIss = `https://${env.ACCESS_TEAM_DOMAIN}`;
  if (payload.iss !== expectedIss) {
    throw new Error(`JWT issuer mismatch: expected ${expectedIss}`);
  }

  if (payload.exp <= nowSec) {
    throw new Error('JWT has expired');
  }

  if (payload.iat > nowSec + 30) {
    // 30 s clock tolerance
    throw new Error('JWT issued in the future');
  }

  return payload;
}
```

---

## Worker Entry Point

```typescript
// src/index.ts
import type { Env } from './env';
import { verifyAccessJwt, type AccessClaims } from './access-auth';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const token = request.headers.get('Cf-Access-Jwt-Assertion');

    if (!token) {
      return new Response('Unauthorized — missing Access JWT', { status: 401 });
    }

    let claims: AccessClaims;
    try {
      claims = await verifyAccessJwt(env, token);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'JWT verification error';
      return new Response(`Forbidden — ${msg}`, { status: 403 });
    }

    // Attach identity to a new header for downstream use
    const downstream = new Request(request, {
      headers: new Headers({
        ...Object.fromEntries(request.headers),
        'X-User-Email': claims.email,
        'X-User-Sub': claims.sub,
      }),
    });

    return handleProtectedRequest(downstream, env, claims);
  },
};

async function handleProtectedRequest(
  request: Request,
  env: Env,
  claims: AccessClaims,
): Promise<Response> {
  return Response.json({ email: claims.email, groups: claims.groups ?? [] });
}
```

---

## Proactive JWKS Warming (Scheduled Worker)

To avoid the first-request latency of a cold KV miss, warm the cache on a schedule:

```typescript
// src/index.ts — add a scheduled handler
export default {
  // ... fetch handler above ...

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    // Force-refresh the JWKS cache every 30 minutes via a Cron Trigger
    const { getJwks } = await import('./jwks-cache');
    await getJwks(env, true);
    console.log('JWKS cache warmed');
  },
};
```

```toml
# wrangler.toml
[triggers]
crons = ["*/30 * * * *"]
```

---

## Anti-patterns

- **Hard-coding the public key PEM or JWK.** This breaks silently when Cloudflare rotates
  keys. Always fetch from the JWKS endpoint.
- **Not retrying on kid-not-found.** Without a retry, the first request after a rotation
  fails until the cache TTL expires.
- **Accepting `alg: 'RS256'` from the JWT header without restriction.** Always enforce
  `RS256` in the import algorithm; do not derive the algorithm from the token.
- **Treating `CF-Connecting-IP` as proof of user identity.** The JWT is the identity
  assertion. IP can change (VPN, IPv6 rotation).
- **Not validating `aud`.** A JWT issued for application A is valid for application B if
  `aud` is not checked — allowing cross-application token replay.
- **Caching JWKS for too long.** Cloudflare can publish new keys with only 24 h advance
  notice. A 24 h+ TTL risks a cache hit against stale keys during the rotation.

---

## Gotchas

- The `Cf-Access-Jwt-Assertion` header is only present when Cloudflare Access is in the
  request path. In local `wrangler dev`, it is absent — mock it in your test harness.
- The JWKS endpoint returns public keys only — there is no private key exposure risk in
  caching or logging the JWKS.
- Access JWTs have a short TTL (typically 20 minutes). If your Worker caches results
  keyed on the JWT itself (e.g., for downstream service calls), ensure the cache TTL is
  shorter than the JWT TTL.
- Groups and identity fields in the JWT payload depend on the identity provider configured
  in Cloudflare Access. Do not assume `email` or `groups` are always present without
  testing with your specific IdP.
- KV `get` with `'json'` type will return `null` (not throw) if the key is absent or
  expired — handle the null case before the rotation-retry logic.

---

## Verification

```bash
# Decode a live Access JWT to inspect claims (does not verify signature)
TOKEN=$(curl -s -I https://protected.example.com \
  | grep -i 'cf-access-jwt-assertion' | awk '{print $2}')

echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq .
```

```typescript
// Integration test: confirm both cached and fresh-fetch paths work
describe('verifyAccessJwt', () => {
  it('succeeds with a valid token and cached JWKS', async () => {
    const token = await mintTestAccessToken(env);
    const claims = await verifyAccessJwt(env, token);
    expect(claims.email).toBe('test@example.com');
  });

  it('re-fetches JWKS when kid is unknown', async () => {
    // Poison the cache with a JWKS that does not contain the token's kid
    await env.JWKS_CACHE.put('access-jwks', JSON.stringify({ keys: [] }));
    const token = await mintTestAccessToken(env);
    // Should force-refresh and succeed
    await expect(verifyAccessJwt(env, token)).resolves.toBeDefined();
  });
});
```

---

## Related

- `cloudflare-access-jwt-assertion-validation.md`
- `cloudflare-access-jwt-claims-rbac-workers.md`
- `cloudflare-access-bypass-prevention.md`
- `jwt-algorithm-confusion-attack.md`
- `oauth-token-introspection-workers.md`
- `workers-kv-ttl-token-revocation-expiry.md`

---

## Sources

- Cloudflare Access JWT validation — https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
- Cloudflare Access JWKS endpoint — https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/application-token/
- RFC 7517 JSON Web Key — https://datatracker.ietf.org/doc/html/rfc7517
- RFC 7515 JSON Web Signature — https://datatracker.ietf.org/doc/html/rfc7515
- RFC 8725 JWT Best Current Practices — https://datatracker.ietf.org/doc/html/rfc8725
