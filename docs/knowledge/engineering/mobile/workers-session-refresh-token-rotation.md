# JWT Session + Refresh Token Rotation for Mobile in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Mobile sessions need to stay alive across days or weeks without requiring re-login, yet a stolen token must be revocable instantly. A naive long-lived JWT solves persistence but cannot be revoked. A refresh-token rotation scheme issues short-lived access tokens (15 minutes) backed by long-lived refresh tokens (30 days) that are rotated and revoked on every use, preventing replay attacks even if a token is intercepted.

## Context

A Cloudflare Worker handles `POST /auth/token/refresh`. Refresh tokens are stored in D1 with their family, device fingerprint, and expiry. On refresh, the old token is revoked and a new one issued atomically. A KV lock prevents concurrent refresh races from a single device. `POST /auth/logout-all` invalidates all tokens for a user by deleting the token family. Access tokens are short-lived HS256 JWTs verified entirely at the edge without a D1 lookup.

## Solution

```typescript
// token-rotation/src/index.ts
import { Hono } from 'hono';

export interface Env {
  REFRESH_TOKENS: D1Database;
  REFRESH_LOCK: KVNamespace;   // distributed lock: key=userId:deviceId => lockToken, TTL 10s
  JWT_SECRET: string;
  REFRESH_SECRET: string;
}

const ACCESS_TOKEN_TTL  = 15 * 60;         // 15 minutes
const REFRESH_TOKEN_TTL = 30 * 24 * 60 * 60; // 30 days

// ── Crypto helpers ─────────────────────────────────────────────────────────────

function b64url(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

function b64urlDecode(s: string): ArrayBuffer {
  const base64 = s.replace(/-/g, '+').replace(/_/g, '/');
  return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0)).buffer;
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw', new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify'],
  );
}

async function signJwt(
  payload: Record<string, unknown>,
  secret: string,
): Promise<string> {
  const hdr = b64url(new TextEncoder().encode(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).buffer);
  const pld = b64url(new TextEncoder().encode(JSON.stringify(payload)).buffer);
  const input = `${hdr}.${pld}`;
  const key = await hmacKey(secret);
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(input));
  return `${input}.${b64url(sig)}`;
}

async function verifyJwt(
  token: string,
  secret: string,
): Promise<Record<string, unknown> | null> {
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  const [hdr, pld, sig] = parts;
  const key = await hmacKey(secret);
  const valid = await crypto.subtle.verify(
    'HMAC', key,
    b64urlDecode(sig),
    new TextEncoder().encode(`${hdr}.${pld}`),
  );
  if (!valid) return null;
  const payload = JSON.parse(new TextDecoder().decode(b64urlDecode(pld)));
  if (payload.exp && payload.exp < Math.floor(Date.now() / 1000)) return null;
  return payload;
}

function randomToken(bytes = 32): string {
  return b64url(crypto.getRandomValues(new Uint8Array(bytes)).buffer);
}

// ── KV distributed lock ────────────────────────────────────────────────────────

async function acquireLock(
  kv: KVNamespace,
  lockKey: string,
  ttl = 10,
): Promise<string | null> {
  const lockToken = randomToken(16);
  // KV put with nx-equivalent: putIfAbsent is not native, so we use a get-then-put
  // with a very short window. For true atomic lock use a DO; this is a best-effort lock.
  const existing = await kv.get(lockKey);
  if (existing) return null; // lock held
  await kv.put(lockKey, lockToken, { expirationTtl: ttl });
  // Verify we won the race (re-read)
  const check = await kv.get(lockKey);
  return check === lockToken ? lockToken : null;
}

async function releaseLock(
  kv: KVNamespace,
  lockKey: string,
  lockToken: string,
): Promise<void> {
  const current = await kv.get(lockKey);
  if (current === lockToken) await kv.delete(lockKey);
}

// ── Routes ─────────────────────────────────────────────────────────────────────

const app = new Hono<{ Bindings: Env }>();

// Issue initial token pair (called after successful login/biometric verify)
app.post('/auth/token/issue', async (c) => {
  const { user_id, device_id, device_fingerprint } = await c.req.json<{
    user_id: string;
    device_id: string;
    device_fingerprint: string;
  }>();

  if (!user_id || !device_id) return c.json({ error: 'user_id and device_id required' }, 400);

  const family = randomToken(16);       // token family — all rotated tokens share this
  const refreshToken = randomToken(32);
  const now = Math.floor(Date.now() / 1000);
  const expiresAt = new Date((now + REFRESH_TOKEN_TTL) * 1000).toISOString();

  await c.env.REFRESH_TOKENS
    .prepare(
      `INSERT INTO refresh_tokens
         (token, family, user_id, device_id, device_fingerprint, expires_at, revoked)
       VALUES (?, ?, ?, ?, ?, ?, 0)`,
    )
    .bind(refreshToken, family, user_id, device_id, device_fingerprint, expiresAt)
    .run();

  const accessToken = await signJwt(
    { sub: user_id, did: device_id, iat: now, exp: now + ACCESS_TOKEN_TTL },
    c.env.JWT_SECRET,
  );

  return c.json({
    access_token: <redacted-secret>
    refresh_token: refreshToken,
    expires_in: ACCESS_TOKEN_TTL,
    token_type: 'Bearer',
  });
});

// Rotate refresh token
app.post('/auth/token/refresh', async (c) => {
  const { refresh_token, device_id, device_fingerprint } = await c.req.json<{
    refresh_token: string;
    device_id: string;
    device_fingerprint: string;
  }>();

  if (!refresh_token || !device_id) return c.json({ error: 'Missing fields' }, 400);

  // 1. Load stored token
  const stored = await c.env.REFRESH_TOKENS
    .prepare(
      'SELECT * FROM refresh_tokens WHERE token = ?',
    )
    .bind(refresh_token)
    .first<{
      token: string; family: string; user_id: string; device_id: string;
      device_fingerprint: string; expires_at: string; revoked: number;
    }>();

  if (!stored) return c.json({ error: 'Invalid token' }, 401);
  if (stored.revoked) {
    // Token reuse detected — invalidate entire family (possible theft)
    await c.env.REFRESH_TOKENS
      .prepare('UPDATE refresh_tokens SET revoked = 1 WHERE family = ?')
      .bind(stored.family)
      .run();
    return c.json({ error: 'Token reuse detected; please log in again' }, 401);
  }
  if (new Date(stored.expires_at) < new Date()) return c.json({ error: 'Token expired' }, 401);
  if (stored.device_id !== device_id) return c.json({ error: 'Device mismatch' }, 401);

  // 2. Acquire per-device lock to prevent concurrent refresh races
  const lockKey = `lock:${stored.user_id}:${device_id}`;
  const lockToken = await acquireLock(c.env.REFRESH_LOCK, lockKey);
  if (!lockToken) return c.json({ error: 'Refresh already in progress; retry in 5s' }, 429);

  try {
    // 3. Revoke old token and issue new one (within lock)
    const newRefreshToken = randomToken(32);
    const now = Math.floor(Date.now() / 1000);
    const expiresAt = new Date((now + REFRESH_TOKEN_TTL) * 1000).toISOString();

    await c.env.REFRESH_TOKENS.batch([
      c.env.REFRESH_TOKENS.prepare('UPDATE refresh_tokens SET revoked = 1 WHERE token = ?').bind(refresh_token),
      c.env.REFRESH_TOKENS.prepare(
        `INSERT INTO refresh_tokens
           (token, family, user_id, device_id, device_fingerprint, expires_at, revoked)
         VALUES (?, ?, ?, ?, ?, ?, 0)`,
      ).bind(newRefreshToken, stored.family, stored.user_id, device_id, device_fingerprint, expiresAt),
    ]);

    const accessToken = await signJwt(
      { sub: stored.user_id, did: device_id, iat: now, exp: now + ACCESS_TOKEN_TTL },
      c.env.JWT_SECRET,
    );

    return c.json({
      access_token: <redacted-secret>
      refresh_token: newRefreshToken,
      expires_in: ACCESS_TOKEN_TTL,
      token_type: 'Bearer',
    });
  } finally {
    await releaseLock(c.env.REFRESH_LOCK, lockKey, lockToken);
  }
});

// Logout from all devices
app.post('/auth/logout-all', async (c) => {
  const payload = await verifyJwt(
    (c.req.header('Authorization') ?? '').replace('Bearer ', ''),
    c.env.JWT_SECRET,
  );
  if (!payload) return c.json({ error: 'Unauthorized' }, 401);

  await c.env.REFRESH_TOKENS
    .prepare('UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?')
    .bind(payload.sub as string)
    .run();

  return c.json({ ok: true });
});

export default app;
```

## Implementation Details

**D1 schema:**
```sql
CREATE TABLE refresh_tokens (
  token              TEXT PRIMARY KEY,
  family             TEXT NOT NULL,
  user_id            TEXT NOT NULL,
  device_id          TEXT NOT NULL,
  device_fingerprint TEXT,
  expires_at         TEXT NOT NULL,
  revoked            INTEGER NOT NULL DEFAULT 0,
  created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_rt_user   ON refresh_tokens(user_id);
CREATE INDEX idx_rt_family ON refresh_tokens(family);
```

**Token rotation logic** — every call to `/auth/token/refresh` revokes the presented token and inserts a fresh one in a D1 `batch()` call (both statements execute atomically within D1's single-writer constraint). If an attacker replays a revoked token, the family is entirely invalidated, forcing re-authentication on all devices.

**KV lock rationale** — iOS and Android apps can trigger simultaneous refresh calls (background fetch + foreground resume). Without a lock, two concurrent refreshes can both see the token as valid and issue duplicate new tokens, leaving one device with an already-revoked token. The KV lock reduces this race to a 429 with a retry hint.

**Access token verification** — short-lived JWTs are verified at any Worker or edge function without a D1 lookup (HMAC verify only). The `did` claim binds the token to a device ID; downstream services can reject tokens used from an unexpected device.

**Cleanup** — run a nightly Scheduled Worker to `DELETE FROM refresh_tokens WHERE expires_at < datetime('now') AND revoked = 1` to keep the table compact.

## Anti-patterns

- **Long-lived access tokens.** A 24-hour JWT that cannot be revoked is effectively a password. Keep access tokens at 15 minutes maximum.
- **Not invalidating the whole family on reuse.** If you only revoke the single presented token without checking for reuse, an attacker who stole a token can still rotate it.
- **Storing access tokens in D1.** Every API call would require a D1 lookup, adding 10–30ms of latency. Verify access tokens cryptographically at the edge; only refresh tokens need database storage.
- **Device fingerprint as the sole security control.** Device fingerprints can be spoofed. Use them as a signal for anomaly detection (log mismatches), not as a hard gate.

## Gotchas

- KV `put` is not atomic with a conditional check. The `acquireLock` implementation above has a small race window. For high-concurrency apps, replace the KV lock with a Durable Object that implements a proper `compare-and-swap`.
- D1 `batch()` is not a true ACID transaction on all configurations — check the Cloudflare docs for your D1 plan's transaction semantics before relying on it for revocation atomicity.
- `verifyJwt` returns `null` for both expired and tampered tokens. Log which case occurred (check `exp` separately) for security monitoring.
- The 30-day refresh token TTL is a UX choice. Finance apps may want 7 days; social apps 90 days. Make `REFRESH_TOKEN_TTL` a KV-configurable value rather than a hard-coded constant.

## Verification

```bash
# Issue initial token pair
TOKENS=$(curl -s -X POST https://api.example.com/auth/token/issue \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"u1","device_id":"d1","device_fingerprint":"fp123"}')
ACCESS=$(echo $TOKENS | jq -r .access_token)
REFRESH=$(echo $TOKENS | jq -r .refresh_token)

# Rotate
NEW=$(curl -s -X POST https://api.example.com/auth/token/refresh \
  -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"$REFRESH\",\"device_id\":\"d1\",\"device_fingerprint\":\"fp123\"}")
echo $NEW | jq .

# Replay old refresh token — expect 401 + family invalidation
curl -s -X POST https://api.example.com/auth/token/refresh \
  -H 'Content-Type: application/json' \
  -d "{\"refresh_token\":\"$REFRESH\",\"device_id\":\"d1\",\"device_fingerprint\":\"fp123\"}" | jq .

# Logout all devices
curl -s -X POST https://api.example.com/auth/logout-all \
  -H "Authorization: Bearer $ACCESS" | jq .
```

## Related

- `documentation/docs/policies/mobile/workers-mobile-auth-biometric.md` — biometric login issues the initial token pair
- `documentation/docs/policies/mobile/push-notification-fcm-apns.md` — push token re-registration after logout-all
- `documentation/docs/policies/mobile/workers-app-config-remote.md` — configurable TTLs via remote config

## Sources

- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700
- Refresh token rotation (Auth0 reference): https://auth0.com/docs/secure/tokens/refresh-tokens/refresh-token-rotation
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
- Cloudflare KV: https://developers.cloudflare.com/kv/
