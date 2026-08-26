# Secure JWT Refresh Token Rotation in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
Your Workers-based auth service issues JWTs but short-lived access tokens force frequent re-authentication. You need refresh token rotation where each refresh token is single-use, reuse is detected (indicating theft), and an entire token family is revoked on any anomaly.

---

## Context
Access tokens expire in 15 minutes; refresh tokens in 7 days. Every time a refresh token is consumed, a new refresh token is issued and the old one is marked `used_at`. If a refresh token arrives and `used_at IS NOT NULL`, the entire family (same `family_id`) is revoked — this detects token theft where an attacker replays a stolen token before the legitimate user does. Refresh tokens travel only via `HttpOnly; Secure; SameSite=Strict` cookies to prevent JS access.

---

## D1 Schema
```sql
CREATE TABLE IF NOT EXISTS refresh_tokens (
  id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  token_hash TEXT NOT NULL UNIQUE,
  user_id    TEXT NOT NULL,
  family_id  TEXT NOT NULL,
  issued_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  expires_at INTEGER NOT NULL,
  used_at    INTEGER,
  revoked    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_rt_user   ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_rt_family ON refresh_tokens(family_id);
```

---

## JWT Helpers
```typescript
// src/jwt.ts
const ALG = { name: 'HMAC', hash: 'SHA-256' };

async function importKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    ALG,
    false,
    ['sign', 'verify']
  );
}

function b64url(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

export async function signJwt(
  payload: Record<string, unknown>,
  secret: string
): Promise<string> {
  const header = b64url(new TextEncoder().encode(JSON.stringify({ alg: 'HS256', typ: 'JWT' })));
  const body   = b64url(new TextEncoder().encode(JSON.stringify(payload)));
  const key    = await importKey(secret);
  const sig    = await crypto.subtle.sign(ALG, key, new TextEncoder().encode(`${header}.${body}`));
  return `${header}.${body}.${b64url(sig)}`;
}

export async function verifyJwt(
  token: string,
  secret: string
): Promise<Record<string, unknown> | null> {
  const [h, b, s] = token.split('.');
  if (!h || !b || !s) return null;
  const key = await importKey(secret);
  const valid = await crypto.subtle.verify(
    ALG,
    key,
    Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0)),
    new TextEncoder().encode(`${h}.${b}`)
  );
  if (!valid) return null;
  const payload = JSON.parse(atob(b.replace(/-/g, '+').replace(/_/g, '/'))) as Record<string, unknown>;
  const exp = payload['exp'] as number | undefined;
  if (exp && exp < Math.floor(Date.now() / 1000)) return null;
  return payload;
}
```

---

## Refresh Token Rotation Handler
```typescript
// src/auth.ts
import type { Env } from './env';
import { signJwt, verifyJwt } from './jwt';

const ACCESS_TTL  = 15 * 60;      // 15 minutes
const REFRESH_TTL = 7 * 86400;    // 7 days

async function hashToken(raw: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}

function generateRefreshToken(): string {
  const arr = new Uint8Array(32);
  crypto.getRandomValues(arr);
  return Array.from(arr).map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function handleRefresh(request: Request, env: Env): Promise<Response> {
  // 1. Extract refresh token from HttpOnly cookie
  const cookieHeader = request.headers.get('Cookie') ?? '';
  const match = cookieHeader.match(/refresh_token=([^;]+)/);
  if (!match) return new Response('No refresh token', { status: 401 });

  const rawToken = match[1];
  const tokenHash = await hashToken(rawToken);
  const now = Math.floor(Date.now() / 1000);

  // 2. Look up the token
  const row = await env.DB.prepare(
    `SELECT id, user_id, family_id, expires_at, used_at, revoked
     FROM refresh_tokens WHERE token_hash = ?`
  ).bind(tokenHash).first<{
    id: string; user_id: string; family_id: string;
    expires_at: number; used_at: number | null; revoked: number;
  }>();

  if (!row || row.revoked || row.expires_at < now) {
    return new Response('Invalid or expired refresh token', { status: 401 });
  }

  // 3. Reuse attack detection
  if (row.used_at !== null) {
    // Revoke entire family immediately
    await env.DB.prepare(
      `UPDATE refresh_tokens SET revoked = 1 WHERE family_id = ?`
    ).bind(row.family_id).run();
    console.warn(`Refresh token reuse detected for family ${row.family_id}, user ${row.user_id}`);
    return new Response('Token reuse detected — all sessions revoked', { status: 401 });
  }

  // 4. Mark old token as used
  await env.DB.prepare(
    `UPDATE refresh_tokens SET used_at = ? WHERE id = ?`
  ).bind(now, row.id).run();

  // 5. Issue new refresh token
  const newRaw   = generateRefreshToken();
  const newHash  = await hashToken(newRaw);
  await env.DB.prepare(
    `INSERT INTO refresh_tokens (token_hash, user_id, family_id, issued_at, expires_at)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(newHash, row.user_id, row.family_id, now, now + REFRESH_TTL).run();

  // 6. Issue new access token
  const accessToken = await signJwt(
    { sub: row.user_id, iat: now, exp: now + ACCESS_TTL },
    env.JWT_SECRET
  );

  // 7. Return access token in body, refresh token in HttpOnly cookie
  return new Response(JSON.stringify({ access_token: accessToken }), {
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': [
        `refresh_token=${newRaw}`,
        'HttpOnly',
        'Secure',
        'SameSite=Strict',
        `Max-Age=${REFRESH_TTL}`,
        'Path=/auth/refresh',
      ].join('; '),
    },
  });
}

export async function handleLogin(request: Request, env: Env): Promise<Response> {
  const { username, password } = await request.json<{ username: string; password: string }>();
  // ... verify credentials against D1 ...
  const userId   = 'user-123'; // replace with real lookup
  const familyId = crypto.randomUUID();
  const now      = Math.floor(Date.now() / 1000);

  const rawRefresh   = generateRefreshToken();
  const refreshHash  = await hashToken(rawRefresh);
  await env.DB.prepare(
    `INSERT INTO refresh_tokens (token_hash, user_id, family_id, issued_at, expires_at)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(refreshHash, userId, familyId, now, now + REFRESH_TTL).run();

  const accessToken = await signJwt({ sub: userId, iat: now, exp: now + ACCESS_TTL }, env.JWT_SECRET);

  return new Response(JSON.stringify({ access_token: accessToken }), {
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': [
        `refresh_token=${rawRefresh}`,
        'HttpOnly', 'Secure', 'SameSite=Strict',
        `Max-Age=${REFRESH_TTL}`, 'Path=/auth/refresh',
      ].join('; '),
    },
  });
}
```

---

## Anti-patterns
- **Storing refresh tokens in localStorage** — JS-accessible storage exposes tokens to XSS; use `HttpOnly` cookies.
- **Single-use without reuse detection** — invalidating on use is not enough; you must also detect and respond to reuse.
- **Long-lived access tokens** — access tokens should be short-lived (≤15 min); the refresh mechanism compensates.
- **No family_id grouping** — without it you cannot revoke all tokens for a compromised session chain.

---

## Gotchas
- `SameSite=Strict` prevents cookie being sent on cross-site navigations; use `SameSite=Lax` if your auth is on a different subdomain from the app.
- D1 `used_at` must be nullable; the schema `INTEGER` with no `NOT NULL` allows `NULL` which is how you detect first use.
- Workers do not persist in-memory state between requests; never cache token state in a module-level variable.
- The `Path=/auth/refresh` cookie scope means the refresh token cookie is only sent to that specific path.

---

## Verification
```bash
# Apply schema
wrangler d1 execute my-db --file schema.sql

# Login and capture cookie
curl -c cookies.txt -X POST https://<worker>.workers.dev/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice","password":"secret"}'

# Use refresh token
curl -b cookies.txt -c cookies.txt https://<worker>.workers.dev/auth/refresh

# Simulate reuse attack: send same cookie again
curl -b cookies.txt https://<worker>.workers.dev/auth/refresh
# Expect: 401 Token reuse detected

# Confirm family is revoked in D1
wrangler d1 execute my-db \
  --command "SELECT family_id, revoked FROM refresh_tokens LIMIT 10"
```

---

## Related
- `workers-api-key-rotation-kv-d1.md`
- `workers-bot-detection-cf-turnstile.md`

---

## Sources
- OWASP Refresh Token Rotation — https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- Cloudflare D1 Docs — https://developers.cloudflare.com/d1/
- RFC 6749 OAuth 2.0 — https://datatracker.ietf.org/doc/html/rfc6749
