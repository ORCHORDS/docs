# OIDC JWT Validation at the Workers Edge

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your Workers API is protected by an external OpenID Connect identity provider (Auth0, Okta, Azure AD, Google, Keycloak). Every API request carries a Bearer JWT in the `Authorization` header. You need to verify the token's signature, expiry, audience, and issuer at the Cloudflare edge—before the request touches your D1 database or KV store—without adding latency by calling the IdP on every request.

---

## Context

OpenID Connect (OIDC) ID tokens and OAuth 2.0 access tokens issued by standards-compliant IdPs follow RFC 7519 (JWT) and use asymmetric RS256/ES256 signing. The IdP publishes its public keys at a JWKS endpoint discoverable via the `/.well-known/openid-configuration` metadata document. Workers can fetch these keys once, cache them in KV with a TTL, and verify tokens offline on every subsequent request—achieving sub-millisecond validation at global PoPs with zero IdP round-trips on the hot path.

This is distinct from Cloudflare Access JWT validation (which uses a Cloudflare-specific header and JWKS endpoint); this pattern handles any standards-compliant OIDC provider.

---

## OIDC Discovery and JWKS Caching

```typescript
// workers/src/oidc-discovery.ts
export interface OIDCConfig {
  issuer: string;
  jwksUri: string;
  supportedAlgorithms: string[];
}

export interface CachedJWKS {
  keys: JsonWebKey[];
  fetchedAt: number;
}

const JWKS_CACHE_TTL_MS = 3_600_000; // 1 hour

export async function getOIDCConfig(
  issuerUrl: string,
  kv: KVNamespace
): Promise<OIDCConfig> {
  const cacheKey = `oidc:config:${issuerUrl}`;
  const cached = await kv.get<OIDCConfig>(cacheKey, "json");
  if (cached) return cached;

  const discoveryUrl = `${issuerUrl.replace(/\/$/, "")}/.well-known/openid-configuration`;
  const resp = await fetch(discoveryUrl);
  if (!resp.ok) throw new Error(`OIDC discovery failed: ${resp.status} ${discoveryUrl}`);

  const doc = await resp.json<Record<string, unknown>>();
  const config: OIDCConfig = {
    issuer: doc.issuer as string,
    jwksUri: doc.jwks_uri as string,
    supportedAlgorithms: (doc.id_token_signing_alg_values_supported as string[]) ?? ["RS256"],
  };

  await kv.put(cacheKey, JSON.stringify(config), { expirationTtl: 86400 });
  return config;
}

export async function getJWKS(
  jwksUri: string,
  kv: KVNamespace
): Promise<JsonWebKey[]> {
  const cacheKey = `oidc:jwks:${jwksUri}`;
  const cached = await kv.get<CachedJWKS>(cacheKey, "json");

  if (cached && Date.now() - cached.fetchedAt < JWKS_CACHE_TTL_MS) {
    return cached.keys;
  }

  const resp = await fetch(jwksUri);
  if (!resp.ok) throw new Error(`JWKS fetch failed: ${resp.status} ${jwksUri}`);

  const data = await resp.json<{ keys: JsonWebKey[] }>();
  await kv.put(
    cacheKey,
    JSON.stringify({ keys: data.keys, fetchedAt: Date.now() }),
    { expirationTtl: 3600 }
  );

  return data.keys;
}
```

---

## JWT Header Parsing and Algorithm Validation

```typescript
// workers/src/jwt-parse.ts

export interface JWTHeader {
  alg: string;
  kid?: string;
  typ?: string;
}

export interface JWTClaims {
  iss: string;
  sub: string;
  aud: string | string[];
  exp: number;
  iat: number;
  nbf?: number;
  email?: string;
  scope?: string;

}

const ALLOWED_ALGORITHMS = new Set(["RS256", "ES256", "RS384", "ES384"]);
// Never allow symmetric algorithms from external IdPs
const DENIED_ALGORITHMS = new Set(["HS256", "HS384", "HS512", "none", ""]);

export function parseJWT(token: string): {
  header: JWTHeader;
  claims: JWTClaims;
  signingInput: string;
  signature: Uint8Array;
} {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("JWT must have exactly 3 parts");

  const [headerB64, payloadB64, sigB64] = parts;

  const header = JSON.parse(atob(headerB64.replace(/-/g, "+").replace(/_/g, "/"))) as JWTHeader;
  const claims = JSON.parse(atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/"))) as JWTClaims;

  if (DENIED_ALGORITHMS.has(header.alg)) {
    throw new Error(`Algorithm '${header.alg}' is not permitted`);
  }
  if (!ALLOWED_ALGORITHMS.has(header.alg)) {
    throw new Error(`Unknown algorithm '${header.alg}'`);
  }

  const sigBytes = Uint8Array.from(
    atob(sigB64.replace(/-/g, "+").replace(/_/g, "/")),
    c => c.charCodeAt(0)
  );

  return {
    header,
    claims,
    signingInput: `${headerB64}.${payloadB64}`,
    signature: sigBytes,
  };
}
```

---

## Signature Verification with SubtleCrypto

```typescript
// workers/src/jwt-verify.ts
import { getJWKS } from "./oidc-discovery";
import { parseJWT, type JWTClaims } from "./jwt-parse";

type AlgorithmSpec =
  | { name: "RSASSA-PKCS1-v1_5"; hash: string }
  | { name: "ECDSA"; namedCurve: string; hash: string };

function algorithmSpec(alg: string): AlgorithmSpec {
  switch (alg) {
    case "RS256": return { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" };
    case "RS384": return { name: "RSASSA-PKCS1-v1_5", hash: "SHA-384" };
    case "ES256": return { name: "ECDSA", namedCurve: "P-256", hash: "SHA-256" };
    case "ES384": return { name: "ECDSA", namedCurve: "P-384", hash: "SHA-384" };
    default: throw new Error(`Unsupported algorithm: ${alg}`);
  }
}

export interface VerifyOptions {
  issuer: string;
  audience: string;
  clockSkewSeconds?: number;
}

export async function verifyOIDCToken(
  token: string,
  jwksUri: string,
  options: VerifyOptions,
  kv: KVNamespace
): Promise<JWTClaims> {
  const { header, claims, signingInput, signature } = parseJWT(token);

  // Claims validation
  const now = Math.floor(Date.now() / 1000);
  const skew = options.clockSkewSeconds ?? 30;

  if (claims.iss !== options.issuer) {
    throw new Error(`Issuer mismatch: got '${claims.iss}', expected '${options.issuer}'`);
  }

  const aud = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!aud.includes(options.audience)) {
    throw new Error(`Audience mismatch: '${options.audience}' not in [${aud.join(",")}]`);
  }

  if (now > claims.exp + skew) {
    throw new Error(`Token expired at ${new Date(claims.exp * 1000).toISOString()}`);
  }

  if (claims.nbf && now < claims.nbf - skew) {
    throw new Error("Token not yet valid (nbf)");
  }

  // Signature verification: try matching kid first, then all keys
  const keys = await getJWKS(jwksUri, kv);
  const candidateKeys = header.kid
    ? keys.filter((k) => (k as { kid?: string }).kid === header.kid)
    : keys;

  if (candidateKeys.length === 0) {
    // kid not found — refresh JWKS (key rotation)
    throw new Error("Signing key not found; JWKS may need refresh");
  }

  const spec = algorithmSpec(header.alg);
  const inputBytes = new TextEncoder().encode(signingInput);

  for (const jwk of candidateKeys) {
    try {
      const cryptoKey = await crypto.subtle.importKey(
        "jwk",
        jwk,
        spec,
        false,
        ["verify"]
      );
      const valid = await crypto.subtle.verify(spec, cryptoKey, signature, inputBytes);
      if (valid) return claims;
    } catch {
      // Try next key
    }
  }

  throw new Error("JWT signature verification failed");
}
```

---

## Worker Middleware Integration

```typescript
// workers/src/index.ts
import { getOIDCConfig, getJWKS } from "./oidc-discovery";
import { verifyOIDCToken } from "./jwt-verify";
import type { Env } from "./types";

const OIDC_ISSUER = "https://accounts.google.com"; // or your IdP
const API_AUDIENCE = "https://api.yourapp.com";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Extract Bearer token
    const auth = request.headers.get("Authorization") ?? "";
    if (!auth.startsWith("Bearer ")) {
      return new Response("Unauthorized", { status: 401 });
    }
    const token = auth.slice(7);

    let claims;
    try {
      const config = await getOIDCConfig(OIDC_ISSUER, env.KV_AUTH);

      // On kid-not-found, clear JWKS cache and retry once (handles key rotation)
      try {
        claims = await verifyOIDCToken(token, config.jwksUri, {
          issuer: OIDC_ISSUER,
          audience: API_AUDIENCE,
          clockSkewSeconds: 30,
        }, env.KV_AUTH);
      } catch (err) {
        if (err instanceof Error && err.message.includes("key not found")) {
          await env.KV_AUTH.delete(`oidc:jwks:${config.jwksUri}`);
          claims = await verifyOIDCToken(token, config.jwksUri, {
            issuer: OIDC_ISSUER,
            audience: API_AUDIENCE,
          }, env.KV_AUTH);
        } else {
          throw err;
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Token validation failed";
      return new Response(JSON.stringify({ error: msg }), {
        status: 401,
        headers: { "Content-Type": "application/json", "WWW-Authenticate": "Bearer" },
      });
    }

    // Attach verified identity to request context
    const userCtx = { sub: claims.sub, email: claims.email as string | undefined };
    return handleRequest(request, env, userCtx);
  },
};

async function handleRequest(
  request: Request,
  env: Env,
  user: { sub: string; email?: string }
): Promise<Response> {
  return new Response(JSON.stringify({ ok: true, user }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

---

## Scope and Permission Enforcement

```typescript
// workers/src/scope-guard.ts
import type { JWTClaims } from "./jwt-parse";

export function requireScope(claims: JWTClaims, required: string): void {
  const scopes = ((claims.scope as string | undefined) ?? "").split(" ");
  if (!scopes.includes(required)) {
    throw Object.assign(new Error(`Insufficient scope: '${required}' required`), {
      statusCode: 403,
    });
  }
}

// Usage in a route handler:
// requireScope(claims, "data:read");
// requireScope(claims, "admin:write");
```

---

## Anti-patterns

- **Accepting `alg: "none"`**: Always validate the `alg` header against an allowlist before importing the key. The `none` algorithm means no signature is present; a naive validator will accept any payload.
- **Accepting `alg: "HS256"` from public IdPs**: HS256 requires a shared secret. Public IdPs sign with RS256/ES256; if you accept HS256, an attacker can sign tokens with your own client secret as the HMAC key.
- **Not validating `iss` and `aud`**: A token issued by the same IdP for a different application will pass signature verification but should be rejected by audience mismatch.
- **Caching JWKS indefinitely**: IdPs rotate keys regularly. Use a TTL and retry logic on `kid` not found.
- **Logging full JWT tokens**: JWTs carry identity claims; treat them like passwords in logs.
- **Trusting `kid` from the JWT header without cross-referencing JWKS**: Always look up `kid` in your cached JWKS; never use `kid` to construct a key fetch URL (open redirect / SSRF).

---

## Gotchas

- **`aud` can be a string or array**: The OIDC spec allows both; your validation must handle both forms.
- **Clock skew**: Workers run at edge nodes with NTP-synced clocks, but allow ~30 seconds of skew to handle client time drift.
- **JWKS `use` field**: Filter keys by `use: "sig"` when multiple keys are present (signing vs. encryption keys).
- **Token revocation**: JWT validation is offline; a revoked token remains valid until expiry. For high-security operations, call the IdP's token introspection endpoint (`/introspect`) on the hot path.
- **ES256 signature format**: ECDSA signatures in JWTs are DER-encoded; `SubtleCrypto.verify` with `ECDSA` expects raw P1363 format. If verification fails for ES256, convert from DER to P1363 before calling `verify`.

---

## Verification

```bash
# 1. Decode a token to inspect claims (no verification)
echo "$TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq .

# 2. Test with an expired token — expect 401
curl -si https://your-worker.example.com/api/data \
  -H "Authorization: Bearer $EXPIRED_TOKEN"

# 3. Test with a wrong audience — expect 401
curl -si https://your-worker.example.com/api/data \
  -H "Authorization: Bearer $WRONG_AUD_TOKEN"

# 4. Test with a valid token — expect 200
curl -si https://your-worker.example.com/api/data \
  -H "Authorization: Bearer $VALID_TOKEN"

# 5. Verify JWKS is cached in KV after first request
wrangler kv key list --namespace-id $KV_NS_ID | grep oidc
```

---

## Related

- `jwt-best-practices.md`
- `jwt-rfc-8725-validation-profile.md`
- `jwt-algorithm-confusion-attack.md`
- `cloudflare-access-jwt-assertion-validation.md`
- `oauth-jwt-access-token-profile-rfc9068.md`

---

## Sources

- RFC 7519 JWT: https://datatracker.ietf.org/doc/html/rfc7519
- RFC 8725 JWT Best Current Practices: https://datatracker.ietf.org/doc/html/rfc8725
- OIDC Core specification: https://openid.net/specs/openid-connect-core-1_0.html
- Cloudflare Workers SubtleCrypto: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- JWKS RFC 7517: https://datatracker.ietf.org/doc/html/rfc7517
