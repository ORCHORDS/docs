# Cloudflare Access JWT Assertion Validation in Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your Worker sits behind a Cloudflare Access policy, but direct requests that bypass the Access proxy can skip authentication entirely because the Worker trusts the `CF-Access-JWT-Assertion` header without verifying its signature.

## Context
Cloudflare Access injects a signed `CF-Access-JWT-Assertion` header into every request that passes its identity check. An attacker who reaches the Worker's origin URL directly — or who forges the header — can impersonate any user unless the Worker validates the JWT signature against the Access public key set. Cloudflare publishes a JWKS endpoint per-team at `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`. The Worker must fetch those keys, cache them, and verify the token's signature, expiry, `iss`, and `aud` claims on every request.

## Fetching and Caching the JWKS
Fetch the public key set from the Access JWKS endpoint. Cache it in a module-level map (or Workers Cache API) so key fetching does not add latency on every request.

```typescript
interface JWK {
  kty: string;
  kid: string;
  n: string;
  e: string;
  alg: string;
  use: string;
}

const keyCache = new Map<string, CryptoKey>();

async function getPublicKey(kid: string, teamDomain: string): Promise<CryptoKey> {
  if (keyCache.has(kid)) return keyCache.get(kid)!;

  const certsUrl = `https://${teamDomain}/cdn-cgi/access/certs`;
  const resp = await fetch(certsUrl, { cf: { cacheTtl: 600 } });
  if (!resp.ok) throw new Error(`JWKS fetch failed: ${resp.status}`);

  const { keys }: { keys: JWK[] } = await resp.json();
  const jwk = keys.find((k) => k.kid === kid);
  if (!jwk) throw new Error(`kid "${kid}" not found in JWKS`);

  const cryptoKey = await crypto.subtle.importKey(
    "jwk",
    jwk,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["verify"]
  );

  keyCache.set(kid, cryptoKey);
  return cryptoKey;
}
```

## Validating the JWT Signature and Claims
Decode the JWT header to extract `kid`, verify the signature, then check all required claims. Reject the request immediately if any check fails.

```typescript
function base64UrlDecode(s: string): Uint8Array {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/").padEnd(
    s.length + ((4 - (s.length % 4)) % 4),
    "="
  );
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
}

interface AccessClaims {
  sub: string;
  email: string;
  iss: string;
  aud: string[];
  iat: number;
  exp: number;
  identity_nonce?: string;
}

async function validateAccessJWT(
  token: string,
  teamDomain: string,
  audienceTag: string
): Promise<AccessClaims> {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("Malformed JWT");

  const [headerB64, payloadB64, sigB64] = parts;
  const header: { alg: string; kid: string } = JSON.parse(
    new TextDecoder().decode(base64UrlDecode(headerB64))
  );

  if (header.alg !== "RS256") throw new Error(`Unexpected alg: ${header.alg}`);

  const publicKey = await getPublicKey(header.kid, teamDomain);
  const signingInput = new TextEncoder().encode(`${headerB64}.${payloadB64}`);
  const signature = base64UrlDecode(sigB64);

  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    publicKey,
    signature,
    signingInput
  );
  if (!valid) throw new Error("JWT signature invalid");

  const claims: AccessClaims = JSON.parse(
    new TextDecoder().decode(base64UrlDecode(payloadB64))
  );

  const now = Math.floor(Date.now() / 1000);
  if (claims.exp < now) throw new Error("JWT expired");
  if (claims.iat > now + 30) throw new Error("JWT issued in the future");
  if (claims.iss !== `https://${teamDomain}`) throw new Error("Wrong issuer");
  if (!claims.aud.includes(audienceTag)) throw new Error("Wrong audience");

  return claims;
}
```

## Wiring Into the Worker Request Handler
Extract the assertion header and reject unauthenticated requests before any business logic runs. Attach verified identity to the request context.

```typescript
export interface Env {
  CF_ACCESS_TEAM_DOMAIN: string; // e.g. "myteam.cloudflareaccess.com"
  CF_ACCESS_AUD: string;         // Application Audience Tag from the Access dashboard
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const token = request.headers.get("CF-Access-JWT-Assertion");
    if (!token) {
      return new Response("Unauthorized", { status: 401 });
    }

    let claims: AccessClaims;
    try {
      claims = await validateAccessJWT(
        token,
        env.CF_ACCESS_TEAM_DOMAIN,
        env.CF_ACCESS_AUD
      );
    } catch (err) {
      console.log(`ACCESS_DENIED reason="${String(err)}" ray="${request.headers.get("cf-ray")}"`);
      return new Response("Forbidden", { status: 403 });
    }

    // Forward verified identity as a trusted internal header to downstream bindings
    const enriched = new Request(request, {
      headers: {
        ...Object.fromEntries(request.headers),
        "X-Verified-User-Email": claims.email,
        "X-Verified-User-Sub": claims.sub,
      },
    });

    return handleRequest(enriched, claims, env);
  },
};

async function handleRequest(
  _request: Request,
  claims: AccessClaims,
  _env: Env
): Promise<Response> {
  return new Response(JSON.stringify({ user: claims.email }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

## Handling Key Rotation
Access rotates its signing keys periodically. When signature verification fails with a cached key, evict the cache and retry once to pick up the new key without human intervention.

```typescript
async function validateWithRetry(
  token: string,
  teamDomain: string,
  audienceTag: string
): Promise<AccessClaims> {
  try {
    return await validateAccessJWT(token, teamDomain, audienceTag);
  } catch (err) {
    if (String(err).includes("kid") || String(err).includes("signature")) {
      // Possible key rotation — clear cache and retry once
      keyCache.clear();
      return validateAccessJWT(token, teamDomain, audienceTag);
    }
    throw err;
  }
}
```

## Anti-patterns
- Trusting the `CF-Access-JWT-Assertion` header without verifying its signature — any party that reaches the Worker's URL directly can forge it
- Verifying only the signature but skipping `exp`, `iss`, or `aud` claims — allows token reuse across teams or applications
- Storing the public key as a hardcoded string — breaks silently on key rotation
- Caching keys indefinitely without a TTL — stale keys accumulate and the cache grows unbounded over time
- Using the `email` claim for access control without also checking `sub` — email addresses can be reused after account deletion

## Gotchas
- The Audience Tag is a 64-character hex string found in the Access application settings, not the application name
- Cloudflare Access strips the `CF-Access-JWT-Assertion` header from requests that fail the policy, but it does NOT strip it from direct requests that bypass the proxy entirely
- Workers Cache API is per-data-center; the module-level `keyCache` Map is per-isolate, which means the first request on each new isolate will incur a JWKS fetch
- `CF-Access-Authenticated-User-Email` is a convenience header Cloudflare adds — treat it as informational only; always verify the JWT

## Verification
1. Deploy the Worker, then call it directly with no `CF-Access-JWT-Assertion` header: expect `401`.
2. Call it with a tampered JWT (flip one byte of the signature): expect `403`.
3. Call it with an expired token (modify `exp` to a past timestamp after signing): expect `403`.
4. Obtain a valid token from a browser session behind Access and pass it in the header: expect `200`.

## Related
- [Cloudflare Access Service Token Rotation and Emergency Revocation](cloudflare-access-service-token-rotation-and-emergency-revocation.md)
- [Cloudflare Zero Trust mTLS Service Auth](cloudflare-zero-trust-mtls-service-auth.md)
- [JWT RFC-8725 Validation Profile](jwt-rfc-8725-validation-profile.md)
- [Service Binding Zero Trust Workers](service-binding-zero-trust-workers.md)

## Sources
- https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/
- https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-apps/
- https://www.rfc-editor.org/rfc/rfc8725 (JWT Best Current Practices)
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
