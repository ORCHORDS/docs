# RS256 JWT Verification in Workers Using the Web Crypto API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to verify RS256-signed JWTs (issued by Auth0, Clerk, Cognito, or your own IdP) at the edge inside a Cloudflare Worker without installing Node crypto libraries. The Web Crypto API is available globally in the Workers runtime and supports RSA-PKCS1-v1_5 / SHA-256, making it possible to validate tokens entirely in-process with no cold-start overhead from third-party packages.

---

## Context

Cloudflare Workers expose the W3C `SubtleCrypto` interface (`crypto.subtle`) which handles RSA key import and signature verification natively. A JWKS endpoint (e.g. `https://your-idp.com/.well-known/jwks.json`) publishes the public key set used to sign tokens. Importing a JWK is a one-time async operation; once complete the resulting `CryptoKey` object can be cached in module scope across requests on the same isolate, eliminating repeated network round-trips. The standard three-part JWT structure (header.payload.signature, base64url-encoded) must be decoded and the signature verified against the raw header+payload bytes before claims are trusted.

---

## Section 1 — Wrangler Config / KV Binding

```toml
# wrangler.toml
name = "api-gateway"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[vars]
JWKS_URI       = "https://your-idp.com/.well-known/jwks.json"
JWT_ISSUER     = "https://your-idp.com/"
JWT_AUDIENCE   = "https://api.example.com"

[[kv_namespaces]]
binding  = "JWKS_CACHE"
id       = "<your-kv-namespace-id>"
```

---

## Section 2 — Worker Implementation

```typescript
// src/jwt.ts

export interface JwtClaims {
  sub: string;
  iss: string;
  aud: string | string[];
  exp: number;
  iat: number;

}

interface Jwk {
  kid: string;
  kty: string;
  use: string;
  n: string;
  e: string;
  alg: string;
}

interface JwksResponse {
  keys: Jwk[];
}

// Module-scope key cache: survives across requests on the same isolate.
const KEY_CACHE = new Map<string, CryptoKey>();

function base64UrlDecode(input: string): Uint8Array {
  // Pad and convert base64url → base64 → bytes
  const padded = input.replace(/-/g, '+').replace(/_/g, '/')
    + '='.repeat((4 - (input.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

async function fetchJwks(jwksUri: string): Promise<JwksResponse> {
  const res = await fetch(jwksUri, {
    cf: { cacheTtl: 3600, cacheEverything: true },
  });
  if (!res.ok) throw new Error(`JWKS fetch failed: ${res.status}`);
  return res.json<JwksResponse>();
}

async function importPublicKey(jwk: Jwk): Promise<CryptoKey> {
  if (KEY_CACHE.has(jwk.kid)) return KEY_CACHE.get(jwk.kid)!;

  const key = await crypto.subtle.importKey(
    'jwk',
    jwk,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,        // not extractable
    ['verify'],
  );
  KEY_CACHE.set(jwk.kid, key);
  return key;
}

export async function verifyJwt(
  token: string,
  jwksUri: string,
  issuer: string,
  audience: string,
): Promise<JwtClaims> {
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('Malformed JWT');

  const [rawHeader, rawPayload, rawSignature] = parts;

  // 1. Decode header to extract kid + alg
  const header = JSON.parse(new TextDecoder().decode(base64UrlDecode(rawHeader))) as {
    alg: string;
    kid: string;
  };
  if (header.alg !== 'RS256') throw new Error(`Unsupported alg: ${header.alg}`);

  // 2. Fetch JWKS and locate matching key
  const jwks = await fetchJwks(jwksUri);
  const jwk = jwks.keys.find((k) => k.kid === header.kid);
  if (!jwk) throw new Error(`Key not found for kid: ${header.kid}`);

  const cryptoKey = await importPublicKey(jwk);

  // 3. Verify signature over "header.payload"
  const signingInput = new TextEncoder().encode(`${rawHeader}.${rawPayload}`);
  const signature = base64UrlDecode(rawSignature);

  const valid = await crypto.subtle.verify(
    'RSASSA-PKCS1-v1_5',
    cryptoKey,
    signature,
    signingInput,
  );
  if (!valid) throw new Error('JWT signature verification failed');

  // 4. Decode and validate claims
  const claims = JSON.parse(
    new TextDecoder().decode(base64UrlDecode(rawPayload)),
  ) as JwtClaims;

  const now = Math.floor(Date.now() / 1000);
  if (claims.exp <= now) throw new Error('JWT expired');
  if (claims.iss !== issuer) throw new Error(`Invalid issuer: ${claims.iss}`);

  const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!aud.includes(audience)) throw new Error(`Invalid audience: ${String(claims.aud)}`);

  return claims;
}
```

```typescript
// src/index.ts
import { verifyJwt, type JwtClaims } from './jwt';

export interface Env {
  JWKS_URI: string;
  JWT_ISSUER: string;
  JWT_AUDIENCE: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const auth = request.headers.get('Authorization') ?? '';
    if (!auth.startsWith('Bearer ')) {
      return new Response('Unauthorized', { status: 401 });
    }
    const token = auth.slice(7);

    let claims: JwtClaims;
    try {
      claims = await verifyJwt(token, env.JWKS_URI, env.JWT_ISSUER, env.JWT_AUDIENCE);
    } catch (err) {
      return new Response((err as Error).message, { status: 401 });
    }

    return new Response(JSON.stringify({ sub: claims.sub }), {
      headers: { 'Content-Type': 'application/json' },
    });
  },
};
```

---

## Section 3 — Testing / Verification

```typescript
// test/jwt.test.ts  (Vitest + @cloudflare/vitest-pool-workers)
import { describe, it, expect } from 'vitest';
import { SELF } from 'cloudflare:test';

describe('JWT verification', () => {
  it('rejects a request with no Authorization header', async () => {
    const res = await SELF.fetch('https://example.com/protected');
    expect(res.status).toBe(401);
  });

  it('rejects an expired token', async () => {
    // Build a token whose exp is in the past — signature verification
    // will fail first if using a real key; use a pre-signed fixture.
    const expiredToken = process.env.EXPIRED_TOKEN_FIXTURE!;
    const res = await SELF.fetch('https://example.com/protected', {
      headers: { Authorization: `Bearer ${expiredToken}` },
    });
    expect(res.status).toBe(401);
    const body = await res.text();
    expect(body).toMatch(/expired|verification failed/i);
  });
});
```

---

## Anti-patterns

- **Trusting the `alg` header blindly** — always enforce `alg === 'RS256'` server-side; an attacker can set `alg: none` to bypass signature verification.
- **Re-importing the key on every request** — importKey is CPU-expensive; cache the `CryptoKey` in module scope keyed by `kid`.
- **Fetching JWKS on every request without caching** — always pass `cf: { cacheTtl: 3600 }` or cache in KV to avoid cold-path latency and rate-limit errors from the IdP.
- **Skipping `aud` validation** — tokens issued for one service are valid across all services if audience is not checked.

---

## Gotchas

- `crypto.subtle.importKey` is async and returns a `CryptoKey`, not a key string; module-scope `Map` caching is safe because Workers isolates are single-threaded.
- JWKS keys rotate; if verification fails with a known `kid`, flush the cache entry and retry once before returning 401.
- `base64url` differs from standard base64: replace `-`→`+` and `_`→`/` before calling `atob`.
- Workers' `Date.now()` is deterministic but can be frozen during CPU quota accounting; use the request's `cf.now` if sub-second clock skew matters.
- The `exp` claim is in seconds since epoch, not milliseconds.

---

## Verification

```bash
# 1. Deploy
npx wrangler deploy

# 2. Obtain a valid token from your IdP and call the Worker
TOKEN=$(curl -s -X POST https://your-idp.com/oauth/token \
  -d '{"client_id":"...","client_secret":"...","grant_type":"client_credentials","audience":"https://api.example.com"}' \
  -H 'Content-Type: application/json' | jq -r .access_token)

curl -H "Authorization: Bearer $TOKEN" https://api-gateway.<your-subdomain>.workers.dev

# 3. Verify rejection of tampered token
TAMPERED="${TOKEN%.*}.invalidsig"
curl -i -H "Authorization: Bearer $TAMPERED" https://api-gateway.<your-subdomain>.workers.dev
# Expect: HTTP 401

# 4. Run unit tests
npx vitest run
```

---

## Related

- `workers-secrets-rotation-zero-downtime.md`
- `workers-csrf-double-submit-cookie-pattern.md`

---

## Sources

- Cloudflare Workers Web Crypto API — https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- RFC 7519 JSON Web Token — https://datatracker.ietf.org/doc/html/rfc7519
- RFC 7517 JSON Web Key — https://datatracker.ietf.org/doc/html/rfc7517
- OWASP JWT Security Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
