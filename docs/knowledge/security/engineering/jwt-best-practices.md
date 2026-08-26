# jwt-best-practices

**Issue:** JWT — when to use, structure, security
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a "stateless" auth using JWT. The user logs in;
you give them a JWT. They send it on every request. A
user's account is compromised. You want to invalidate
their JWT. You can't. The JWT is valid until it expires.

## Root cause
**JWTs are stateless by design.** Revocation requires
extra infrastructure.

**Source:** IETF — JWT:
https://datatracker.ietf.org/doc/html/rfc7519

> "JSON Web Token (JWT) is a compact, URL-safe means of
> representing claims to be transferred between two
> parties."

## The "JWT structure"

A JWT has 3 parts, separated by `.`:
```
header.payload.signature
```

- **Header:** Algorithm, type
- **Payload:** Claims (iss, sub, exp, iat, custom)
- **Signature:** HMAC or RSA of header + payload

```json
// Header
{
  "alg": "HS256",
  "typ": "JWT"
}

// Payload
{
  "iss": "example.com",
  "sub": "u_123",
  "exp": 1723218600,
  "iat": 1723215000,
  "email": "alice@example.com"
}
```

## The "JWT vs session" choice

| Use case | Use |
|---|---|
| Web app with cookies | Session (server-side) |
| Mobile app | JWT (refresh + access) |
| Service-to-service | JWT or mTLS |
| Short-lived tokens | JWT |
| Long-lived + revocable | Session |

For most web apps, **server-side sessions** are simpler and
more secure. Use **JWT for mobile + service-to-service**.

## The "access + refresh" pattern

For a JWT-based system, use two tokens:
- **Access token:** Short-lived (5-15 min); used for API
  calls
- **Refresh token:** Long-lived (30+ days); used to get new
  access tokens

```ts
async function login(email: string, password: string, env: Env): Promise<{ accessToken: string; refreshToken: string }> {
  const user = await verifyPassword(email, password, env);

  const accessToken = await signJwt({
    sub: user.id,
    iss: 'example.com',
    aud: 'api',
    exp: Math.floor(Date.now() / 1000) + 15 * 60,  // 15 min
    iat: Math.floor(Date.now() / 1000),
  }, env.JWT_SECRET);

  const refreshToken = await signJwt({
    sub: user.id,
    iss: 'example.com',
    aud: 'refresh',
    exp: Math.floor(Date.now() / 1000) + 30 * 24 * 60 * 60,  // 30 days
    iat: Math.floor(Date.now() / 1000),
    jti: crypto.randomUUID(),  // Unique ID for revocation
  }, env.JWT_SECRET);

  // Store the refresh token in the DB
  await env.DB!.prepare(
    `INSERT INTO refresh_tokens (id, user_id, expires_at) VALUES (?, ?, ?)`
  ).bind(refreshToken.jti, user.id, new Date(refreshToken.exp * 1000).toISOString()).run();

  return { accessToken, refreshToken };
}
```

The access token is short; the refresh token is long +
revocable.

## The "JWT signing" pattern

For HMAC (symmetric):
```ts
import { sign, verify } from 'jsonwebtoken';

const token = sign(payload, secret, { algorithm: 'HS256' });
const decoded = verify(token, secret);
```

For RSA (asymmetric):
```ts
import { sign, verify } from 'jsonwebtoken';
import { readFileSync } from 'fs';

const privateKey = <redacted-secret>'private.pem');
const publicKey = readFileSync('public.pem');

const token = sign(payload, privateKey, { algorithm: 'RS256' });
const decoded = verify(token, publicKey);
```

Use **RS256** (asymmetric) for public APIs; **HS256** for
internal use.

## The "JWT verification" pattern

```ts
function verifyToken(token: string, env: Env): JWTPayload | null {
  try {
    return verify(token, env.JWT_PUBLIC_KEY, {
      algorithms: ['RS256'],  // Don't accept other algorithms
      issuer: 'example.com',
      audience: 'api',
    });
  } catch (err) {
    return null;  // Invalid token
  }
}
```

Always specify the algorithm; don't accept "none" or other
algorithms.

## The "JWT revocation" pattern

For revocable JWTs, store the jti in a blacklist:
```ts
async function revokeToken(jti: string, env: Env): Promise<void> {
  await env.KV.put(`revoked:${jti}`, '1', {
    expirationTtl: 86400 * 30,  // 30 days
  });
}

async function isTokenRevoked(jti: string, env: Env): Promise<boolean> {
  const revoked = await env.KV.get(`revoked:${jti}`);
  return !!revoked;
}
```

The blacklist is checked on every request.

## The "JWT" anti-patterns

### 1. JWT in localStorage
- **Issue:** XSS can steal the JWT
- **Fix:** Use HTTP-only cookies for the JWT (or a session)

### 2. "alg: none"
- **Issue:** Attacker can forge tokens
- **Fix:** Always specify the algorithm

### 3. Long-lived access tokens
- **Issue:** A token leak is a long-lived credential
- **Fix:** Short access token (5-15 min) + refresh token

### 4. PII in the JWT
- **Issue:** The JWT is decoded by anyone; PII is exposed
- **Fix:** Only put the user ID in the JWT; fetch PII from
  the server

### 5. No expiration
- **Issue:** The token is valid forever
- **Fix:** Always set `exp`

### 6. JWT for everything
- **Issue:** JWT is not a session; it's a token
- **Fix:** Use JWT for service-to-service; use sessions
  for user auth

## The "JWT in HTTP-only cookie" pattern

For a web app, store the JWT in an HTTP-only cookie:
```ts
response.headers.set('Set-Cookie', `access_token=${accessToken}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=900`);
```

The cookie is HTTP-only; XSS can't steal it.

## The "JWT" libraries choice

- **jsonwebtoken:** Node.js; well-maintained
- **jose:** Universal; supports many algorithms
- **PyJWT:** Python
- **java-jwt:** Java
- **jwt-go:** Go

For most JS/TS projects, **jose** is the modern choice
(supports more algorithms, edge-compatible).

## The "JWT claim" pattern

Standard claims:
- **iss (Issuer):** Who issued the token
- **sub (Subject):** The user ID
- **aud (Audience):** Who the token is for
- **exp (Expiration):** When the token expires
- **iat (Issued at):** When the token was issued
- **nbf (Not before):** The token is not valid before this
- **jti (JWT ID):** Unique ID for revocation

```ts
const payload = {
  iss: 'example.com',
  sub: user.id,
  aud: 'api',
  exp: Math.floor(Date.now() / 1000) + 900,  // 15 min
  iat: Math.floor(Date.now() / 1000),
  jti: crypto.randomUUID(),
};
```

## The "JWT" verification checklist

For every JWT verification:
- [ ] Algorithm is specified
- [ ] Signature is valid
- [ ] Issuer is correct
- [ ] Audience is correct
- [ ] Token is not expired
- [ ] Token is not before nbf
- [ ] jti is not in the blacklist
- [ ] User still exists + is active

## Verification
- **Test:** Token is verified
- **Test:** Expired token is rejected
- **Test:** Revoked token is rejected
- **Test:** Wrong issuer is rejected
- **Pen test:** Annual security review

## Gotchas
- **The "JWT in localStorage" anti-pattern.** XSS can
  steal it. Use HTTP-only cookies.
- **The "alg: none" anti-pattern.** Always specify the
  algorithm.
- **The "no jti for revocation" anti-pattern.** Without
  jti, you can't revoke.
- **The "JWT in URL" anti-pattern.** URLs are in logs;
  the JWT is leaked. Use Authorization header.
- **The "PII in JWT" anti-pattern.** The JWT is decoded
  by anyone. Only put the user ID.
- **The "JWT in a SPA" anti-pattern.** Use cookies; not
  localStorage.

## Related
- `session-cookies-vs-jwt.md`
- `feature-cookbook-auth.md`
- `api-key-authentication.md`
- `oauth-best-practices.md`
- IETF JWT: https://datatracker.ietf.org/doc/html/rfc7519
- IETF JWS: https://datatracker.ietf.org/doc/html/rfc7515
- Auth0: https://auth0.com/docs/secure/tokens/json-web-tokens
