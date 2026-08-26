# JWT Token Rotation and Refresh with Sliding Window Workers KV

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Short-lived JWTs (15-minute access tokens) force clients to re-authenticate frequently,
degrading UX. Long-lived tokens expand the breach window if one is stolen. The standard
solution — refresh tokens — introduces its own risks: a refresh token stored insecurely
on a mobile device or in `localStorage` is as dangerous as a long-lived access token.
The goal is a system where an attacker who intercepts a single refresh token gains only
a narrow window of access, and where token theft is detectable and revocable without
maintaining a full per-token blocklist.

## Context

**Sliding window rotation** solves the revocation problem without a database scan on
every request. The scheme:

1. Issue a short-lived **access token** (JWT, signed, 15 min expiry).
2. Issue a **refresh token** (opaque random string, not a JWT) stored server-side in
   Workers KV alongside its metadata (user ID, generation counter, absolute expiry).
3. When the client presents the refresh token, issue a **new** refresh token
   (rotate), invalidate the old one, and slide the absolute expiry window forward by
   a fixed increment (e.g. 7 days from last use, up to a hard maximum of 90 days).
4. If a refresh token is presented that has already been rotated (i.e., an attacker
   replayed an old token after the legitimate client already rotated it), detect the
   **generation conflict** and immediately revoke the entire token family.

Attack vectors addressed:
- **Refresh token replay**: stolen token used after the legitimate client has already
  rotated it — detected by generation conflict, family revoked.
- **Long-lived session abuse**: absolute expiry cap limits breach window to 90 days
  maximum even if the attacker never triggers rotation detection.
- **Token farming**: each family is keyed by a family ID, allowing per-user family
  enumeration and revocation (e.g., on password change).

## Data Model in Workers KV

```typescript
interface RefreshTokenRecord {
  userId: string;
  familyId: string;         // UUID, stable across rotations in a session
  generation: number;       // incremented on every rotation
  absoluteExpiry: number;   // Unix ms; hard ceiling regardless of activity
  issuedAt: number;         // Unix ms of this generation
  deviceHint: string;       // last 4 chars of User-Agent hash for display
  rotated: boolean;         // true once this token has been exchanged
}
```

KV key scheme:
- `rt:<tokenHash>` → `RefreshTokenRecord` (TTL = absolute expiry)
- `family:<familyId>` → `{ userId, revoked: boolean }` (TTL = absolute expiry)
- `user-families:<userId>` → JSON array of active familyIds

Token value stored in KV is the **SHA-256 hash** of the opaque random token string.
The raw token travels over the wire (and is stored by the client) only once.

## Token Issuance

```typescript
import { SignJWT, importPKCS8 } from 'jose';
import { createHash, randomBytes } from 'node:crypto'; // Workers supports Web Crypto

async function issueTokenPair(
  env: Env,
  userId: string,
  deviceHint: string,
): Promise<{ accessToken: string; refreshToken: string }> {
  // --- Access token (JWT) ---
  const privateKey = await importPKCS8(env.JWT_PRIVATE_KEY, 'ES256');
  const accessToken = await new SignJWT({ sub: userId, scope: 'access' })
    .setProtectedHeader({ alg: 'ES256' })
    .setIssuedAt()
    .setExpirationTime('15m')
    .setAudience(env.JWT_AUDIENCE)
    .setIssuer(env.JWT_ISSUER)
    .sign(privateKey);

  // --- Refresh token (opaque) ---
  const rawToken = crypto.randomUUID() + '-' + crypto.randomUUID(); // 73 chars entropy
  const tokenHash = await hashToken(rawToken);
  const familyId = crypto.randomUUID();
  const now = Date.now();
  const absoluteExpiry = now + 90 * 24 * 60 * 60 * 1000; // 90-day hard cap

  const record: RefreshTokenRecord = {
    userId,
    familyId,
    generation: 0,
    absoluteExpiry,
    issuedAt: now,
    deviceHint,
    rotated: false,
  };

  const ttlSeconds = Math.ceil((absoluteExpiry - now) / 1000);
  await env.AUTH_KV.put(`rt:${tokenHash}`, JSON.stringify(record), {
    expirationTtl: ttlSeconds,
  });
  await env.AUTH_KV.put(`family:${familyId}`, JSON.stringify({ userId, revoked: false }), {
    expirationTtl: ttlSeconds,
  });

  return { accessToken, refreshToken: rawToken };
}

async function hashToken(raw: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
```

## Token Rotation (Sliding Window)

```typescript
async function rotateRefreshToken(
  env: Env,
  rawToken: string,
): Promise<{ accessToken: string; refreshToken: string } | { error: string }> {
  const tokenHash = await hashToken(rawToken);
  const recordJson = await env.AUTH_KV.get(`rt:${tokenHash}`);

  if (!recordJson) {
    // Token not found: either expired naturally or never existed.
    return { error: 'invalid_grant' };
  }

  const record: RefreshTokenRecord = JSON.parse(recordJson);
  const now = Date.now();

  // Check absolute expiry
  if (now > record.absoluteExpiry) {
    await env.AUTH_KV.delete(`rt:${tokenHash}`);
    return { error: 'token_expired' };
  }

  // Check family revocation
  const familyJson = await env.AUTH_KV.get(`family:${record.familyId}`);
  const family = familyJson ? JSON.parse(familyJson) : null;
  if (!family || family.revoked) {
    return { error: 'session_revoked' };
  }

  // *** ROTATION CONFLICT DETECTION ***
  if (record.rotated) {
    // This token was already exchanged. Attacker replay detected.
    // Revoke the entire family immediately.
    await revokeFamily(env, record.familyId, record.absoluteExpiry);
    // Log the security event
    await logSecurityEvent(env, {
      type: 'refresh_token_replay',
      userId: record.userId,
      familyId: record.familyId,
      generation: record.generation,
    });
    return { error: 'session_compromised' };
  }

  // Mark the current token as rotated (do NOT delete yet — we need it for
  // replay detection for a short grace window).
  const rotatedRecord: RefreshTokenRecord = { ...record, rotated: true };
  // Keep rotated token alive for 5 minutes to catch network retry storms
  await env.AUTH_KV.put(`rt:${tokenHash}`, JSON.stringify(rotatedRecord), {
    expirationTtl: 300,
  });

  // Issue new token
  const newRaw = crypto.randomUUID() + '-' + crypto.randomUUID();
  const newHash = await hashToken(newRaw);
  // Slide the window: add 7 days from now, but never exceed the hard cap
  const newExpiry = Math.min(
    now + 7 * 24 * 60 * 60 * 1000,
    record.absoluteExpiry,
  );
  const newRecord: RefreshTokenRecord = {
    userId: record.userId,
    familyId: record.familyId,
    generation: record.generation + 1,
    absoluteExpiry: newExpiry,
    issuedAt: now,
    deviceHint: record.deviceHint,
    rotated: false,
  };
  await env.AUTH_KV.put(`rt:${newHash}`, JSON.stringify(newRecord), {
    expirationTtl: Math.ceil((newExpiry - now) / 1000),
  });

  // Re-issue access token
  const privateKey = await importPKCS8(env.JWT_PRIVATE_KEY, 'ES256');
  const accessToken = await new SignJWT({ sub: record.userId, scope: 'access' })
    .setProtectedHeader({ alg: 'ES256' })
    .setIssuedAt()
    .setExpirationTime('15m')
    .setAudience(env.JWT_AUDIENCE)
    .setIssuer(env.JWT_ISSUER)
    .sign(privateKey);

  return { accessToken, refreshToken: newRaw };
}

async function revokeFamily(env: Env, familyId: string, absoluteExpiry: number): Promise<void> {
  const ttl = Math.max(1, Math.ceil((absoluteExpiry - Date.now()) / 1000));
  await env.AUTH_KV.put(
    `family:${familyId}`,
    JSON.stringify({ revoked: true, revokedAt: new Date().toISOString() }),
    { expirationTtl: ttl },
  );
}
```

## Mobile vs Web Storage Considerations

**Web (browser)**:
- Store the refresh token in an `HttpOnly; Secure; SameSite=Strict` cookie.
- The access JWT can live in memory (JS variable) — no `localStorage`.
- On page reload, call a silent `/refresh` endpoint; the cookie is sent automatically.
- CSRF protection is required on the `/refresh` endpoint because cookies are sent
  automatically. Use a `SameSite=Strict` cookie or double-submit CSRF token.

**Mobile (iOS / Android)**:
- Store the refresh token in the OS secure credential store (Keychain on iOS,
  EncryptedSharedPreferences / Android Keystore on Android).
- Do NOT store in SQLite plaintext, SharedPreferences, or app sandbox files that are
  accessible without lock-screen auth.
- The access token can live in memory or a short-lived secure memory region.
- On app foregrounding, check if the access token has expired (decode without
  verification to read `exp`) and silently rotate before the first API call.
- Biometric unlock before rotation is optional but significantly raises the bar for
  malware that has file-system access but not biometric confirmation.

## Anti-patterns

- **Rotating to a JWT refresh token**: JWTs cannot be efficiently revoked without a
  blocklist. Use opaque tokens for refresh; JWTs only for short-lived access.
- **Deleting the old token immediately on rotation**: a network failure between the
  server issuing the new token and the client receiving it causes the client to lose
  its session permanently. Keep the old token alive (marked `rotated`) for a grace
  window.
- **Storing the raw token in KV**: hash it first. KV is not a secrets store; if a KV
  namespace is inadvertently exposed, raw tokens cannot be used without the hash.
- **Allowing parallel refresh calls on the same token**: two concurrent rotations
  produce a race. Use a Durable Object or KV `putIfAbsent` pattern to serialize
  rotation per family.
- **Not logging rotation conflicts**: replay detection is only useful if it feeds an
  alerting pipeline.
- **Hard-coding 90-day maximums**: enterprise customers may require shorter absolute
  expiries. Drive `absoluteExpiry` from a per-user or per-tenant configuration row.

## Gotchas

- KV is eventually consistent. A `get` after a `put` in the same Worker invocation
  is not guaranteed to return the new value. For rotation, this is acceptable because
  you already hold the record in memory within the same invocation.
- KV `expirationTtl` rounds up to the nearest second and has a minimum of 60 s. The
  5-minute grace window for rotated tokens is well above this minimum.
- Cloudflare KV is global; a rotation in Frankfurt is visible in Singapore within
  ~1–2 s under normal conditions but may lag under partition. This creates a tiny
  window where a replayed token in a far region could succeed before propagation. If
  this is unacceptable, use Durable Objects (strongly consistent) for the rotation
  state.
- Access tokens are JWTs and cannot be revoked without an in-request validation call.
  If an account is compromised, rotate the signing key and issue all users new tokens.
  Maintain at most two active key versions to enable zero-downtime rotation.

## Verification

```bash
# Issue a token pair
TOKEN_RESPONSE=$(curl -s -X POST https://api.example.com/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"correct"}')

REFRESH=$(echo $TOKEN_RESPONSE | jq -r '.refreshToken')
ACCESS=$(echo $TOKEN_RESPONSE | jq -r '.accessToken')

# Rotate once
NEW=$(curl -s -X POST https://api.example.com/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refreshToken\":\"$REFRESH\"}")
NEW_REFRESH=$(echo $NEW | jq -r '.refreshToken')

# Attempt replay of the OLD refresh token — should return session_compromised
curl -s -X POST https://api.example.com/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refreshToken\":\"$REFRESH\"}"
# Expected: {"error":"session_compromised"}

# Verify new token works
curl -s -X POST https://api.example.com/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refreshToken\":\"$NEW_REFRESH\"}"
# Expected: new token pair
```

## Related

- `jwt-best-practices.md`
- `jwt-storage-mobile-workers-auth.md`
- `jwt-algorithm-confusion-attack.md`
- `anonymous-auth-jwt-mobile-storage.md`
- `api-key-rotation-workers-kv-secrets.md`
- `session-fixation-workers-d1-rotation.md`

## Sources

- RFC 6819 — OAuth 2.0 Threat Model: https://www.rfc-editor.org/rfc/rfc6819
- Auth0 Refresh Token Rotation: https://auth0.com/docs/secure/tokens/refresh-tokens/refresh-token-rotation
- Cloudflare Workers KV documentation: https://developers.cloudflare.com/kv/
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
