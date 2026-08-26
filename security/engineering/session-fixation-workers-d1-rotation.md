# Session Fixation and ID Rotation: Workers, D1, and Mobile Concurrent Sessions

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

An anonymous example project user who later verifies an email retains the same session token they had before
verification — an attacker who obtained the pre-verification token can hijack the now-elevated
session. Mobile apps running in the background maintain stale session IDs after a privilege
escalation event. D1 session store has no atomic rotation logic, causing a race condition between
concurrent mobile sessions during token rotation. `Set-Cookie` on the rotation response is ignored
by mobile WebViews using Bearer-token auth.

## Context

example project (example.com) is an anonymous social platform. Users start as fully anonymous (no email, no
persistent identity), can upgrade to a pseudo-anonymous account with email verification, and may
further elevate to a moderator role. Each privilege escalation is a session fixation risk if the
session ID is not rotated at the moment of escalation. Sessions are stored in Cloudflare D1 with
a Workers API layer. Mobile clients use Bearer tokens (not cookies), so rotation must update the
token in the response body and the client must apply the new token to subsequent requests.

---

## Session Fixation Attack on Anonymous Platforms

```
Attack flow (without rotation):
1. Attacker loads https://example.com/ — receives session token S1 (anonymous)
2. Attacker sends S1 to victim via a crafted link or QR code
3. Victim uses S1 to authenticate (email verify) — session becomes elevated
4. Attacker uses S1 → gains access to victim's verified account

Fix:
- On ANY privilege change: invalidate S1, issue S2, return S2 to the client
- S1 must not be usable after rotation
```

---

## D1 Session Schema

```sql
-- migrations/001_sessions.sql
CREATE TABLE IF NOT EXISTS sessions (
  id          TEXT    PRIMARY KEY,       -- session ID (opaque random token, 32 bytes hex)
  user_id     TEXT    NOT NULL,
  privilege   TEXT    NOT NULL CHECK (privilege IN ('anonymous', 'verified', 'moderator')),
  created_at  INTEGER NOT NULL,          -- Unix ms
  last_seen   INTEGER NOT NULL,          -- Unix ms
  rotated_from TEXT,                     -- previous session ID (for audit trail)
  expires_at  INTEGER NOT NULL,          -- Unix ms
  device_hint TEXT,                      -- hashed UA+IP for anomaly detection
  revoked     INTEGER NOT NULL DEFAULT 0 -- 0=active, 1=revoked
);

CREATE INDEX idx_sessions_user ON sessions (user_id, revoked, expires_at);
CREATE INDEX idx_sessions_expires ON sessions (expires_at);
```

---

## Atomic Session Rotation in Workers + D1

D1 does not have stored procedures, but it supports `db.batch()` which executes multiple
statements in a single transaction-like batch. Use this to revoke the old session and create the
new one atomically.

```ts
// workers/src/db/sessions.ts

export interface Session {
  id: string;
  userId: string;
  privilege: 'anonymous' | 'verified' | 'moderator';
  createdAt: number;
  lastSeen: number;
  expiresAt: number;
  revoked: number;
}

function newSessionId(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes).map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Atomically revoke the old session and create a new one with the elevated privilege.
 * Returns the new session ID, or throws if the old session is not found / already revoked.
 */
export async function rotateSession(
  db: D1Database,
  oldSessionId: string,
  newPrivilege: Session['privilege'],
  deviceHint: string,
): Promise<string> {
  const now = Date.now();
  const newId = newSessionId();
  // Session TTL: anonymous=24h, verified=7d, moderator=4h (short for high-privilege)
  const ttlMs: Record<Session['privilege'], number> = {
    anonymous: 24 * 60 * 60 * 1000,
    verified: 7 * 24 * 60 * 60 * 1000,
    moderator: 4 * 60 * 60 * 1000,
  };

  // 1. Read old session (outside batch — we need userId)
  const old = await db
    .prepare('SELECT user_id, privilege, revoked FROM sessions WHERE id = ? AND expires_at > ?')
    .bind(oldSessionId, now)
    .first<{ user_id: string; privilege: string; revoked: number }>();

  if (!old) throw new Error('SESSION_NOT_FOUND');
  if (old.revoked) throw new Error('SESSION_ALREADY_REVOKED');

  // 2. Batch: revoke old + insert new (D1 batch is transactional)
  const results = await db.batch([
    db
      .prepare('UPDATE sessions SET revoked = 1 WHERE id = ? AND revoked = 0')
      .bind(oldSessionId),
    db
      .prepare(
        `INSERT INTO sessions
           (id, user_id, privilege, created_at, last_seen, rotated_from, expires_at, device_hint)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(newId, old.user_id, newPrivilege, now, now, oldSessionId, now + ttlMs[newPrivilege], deviceHint),
  ]);

  // Check first statement actually updated a row (concurrent rotation guard)
  const updateMeta = results[0].meta;
  if (updateMeta.changes === 0) {
    // Another concurrent rotation already revoked this session
    throw new Error('SESSION_CONCURRENT_ROTATION');
  }

  return newId;
}

export async function getSession(db: D1Database, sessionId: string): Promise<Session | null> {
  const now = Date.now();
  return db
    .prepare(
      'SELECT * FROM sessions WHERE id = ? AND revoked = 0 AND expires_at > ?',
    )
    .bind(sessionId, now)
    .first<Session>();
}
```

---

## Privilege Escalation Handler in Workers

```ts
// workers/src/handlers/verifyEmail.ts
import { rotateSession } from '../db/sessions';
import { verifyEmailToken } from '../db/users';

export async function handleEmailVerification(
  request: Request,
  env: Env,
): Promise<Response> {
  const { token, sessionId } = await request.json<{ token: string; sessionId: string }>();

  // 1. Verify the email OTP token
  const userId = await verifyEmailToken(env.DB, token);
  if (!userId) {
    return Response.json({ error: 'INVALID_TOKEN' }, { status: 400 });
  }

  // 2. Rotate session — must happen before returning success
  const deviceHint = await hashDeviceHint(request);
  let newSessionId: string;
  try {
    newSessionId = await rotateSession(env.DB, sessionId, 'verified', deviceHint);
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'ROTATION_FAILED';
    if (msg === 'SESSION_NOT_FOUND' || msg === 'SESSION_ALREADY_REVOKED') {
      return Response.json({ error: 'SESSION_INVALID' }, { status: 401 });
    }
    if (msg === 'SESSION_CONCURRENT_ROTATION') {
      return Response.json({ error: 'CONCURRENT_SESSION' }, { status: 409 });
    }
    throw err;
  }

  // 3. Return new session token in response body (mobile uses Bearer, not cookie)
  return Response.json(
    { sessionToken: newSessionId, privilege: 'verified' },
    {
      status: 200,
      headers: {
        // Cookie for web clients (Belt AND suspenders approach)
        'Set-Cookie': `session=${newSessionId}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=604800`,
      },
    },
  );
}

async function hashDeviceHint(request: Request): Promise<string> {
  const ua = request.headers.get('user-agent') ?? '';
  const ip = request.headers.get('cf-connecting-ip') ?? '';
  const data = new TextEncoder().encode(`${ua}|${ip}`);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash)).map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
}
```

---

## Mobile Concurrent Sessions

Mobile apps run in the background and may hold multiple sessions across devices or after app
reinstall. example project supports concurrent sessions per user with independent rotation.

| Scenario                                      | Behaviour                                      | Resolution                                               |
|-----------------------------------------------|------------------------------------------------|----------------------------------------------------------|
| Two devices rotate simultaneously             | Second batch sees `changes = 0`                | Return 409; mobile retries with fresh session fetch      |
| App in background during email verification   | Background session stale after foreground rotates| App resume triggers `/api/session/refresh` which fails → re-auth |
| Re-install with saved token (Keychain/Keystore)| Token may be revoked if account escalated      | `GET /api/session` returns 401; app prompts re-auth      |
| Moderator actions from mobile                 | 4h TTL; rotation required before each mod action| Client-side TTL check + rotation before escalated calls  |

```ts
// Mobile client (React Native) — handle session rotation response
async function verifyEmail(otp: string): Promise<void> {
  const response = await apiClient.post('/verify-email', {
    token: otp,
    sessionId: await SecureStorage.get('sessionId'),
  });

  if (response.status === 200) {
    // MUST update stored session before any subsequent request
    await SecureStorage.set('sessionId', response.data.sessionToken);
    apiClient.defaults.headers['Authorization'] = `Bearer ${response.data.sessionToken}`;
  } else if (response.status === 409) {
    // Concurrent rotation — fetch current session
    const session = await apiClient.get('/session');
    await SecureStorage.set('sessionId', session.data.sessionToken);
  }
}
```

---

## Token Binding Considerations

Token binding (RFC 8471, now largely deprecated in browsers) is not supported by mobile HTTP
stacks. example project's approach is device hinting instead:

```ts
// workers/src/middleware/sessionAuth.ts
export async function authenticateSession(
  request: Request,
  env: Env,
): Promise<{ session: Session; anomaly: boolean } | null> {
  const token = extractBearerToken(request);
  if (!token) return null;

  const session = await getSession(env.DB, token);
  if (!session) return null;

  // Soft binding — detect device change, log for review, but do not reject
  const deviceHint = await hashDeviceHint(request);
  const anomaly = session.deviceHint !== null && session.deviceHint !== deviceHint;

  if (anomaly) {
    // Log suspicious session use; consider requiring re-auth for sensitive operations
    console.warn(`[SESSION_ANOMALY] session=${token.slice(0, 8)} expected=${session.deviceHint} got=${deviceHint}`);
  }

  // Update last_seen (fire-and-forget; do not block response)
  env.DB.prepare('UPDATE sessions SET last_seen = ? WHERE id = ?')
    .bind(Date.now(), session.id)
    .run();

  return { session, anomaly };
}

function extractBearerToken(request: Request): string | null {
  const auth = request.headers.get('authorization') ?? '';
  const match = auth.match(/^Bearer\s+([A-Za-z0-9_-]{64})$/);
  return match ? match[1] : null;
}
```

---

## Session Expiry and Cleanup

```ts
// workers/src/cron/sessionCleanup.ts  — scheduled via Cron Trigger
export async function cleanupExpiredSessions(db: D1Database): Promise<void> {
  const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000; // keep 30d for audit
  const result = await db
    .prepare('DELETE FROM sessions WHERE expires_at < ? AND revoked = 1')
    .bind(cutoff)
    .run();
  console.log(`[SESSION_CLEANUP] deleted ${result.meta.changes} sessions`);
}
```

---

## Anti-patterns

- Not rotating the session on email verification, phone verification, or role elevation — any
  privilege change without rotation is a session fixation vulnerability.
- Rotating only the session cookie but not the Bearer token (or vice versa) — both must be
  updated atomically; split rotation leaves one channel exploitable.
- Soft-deleting (marking `revoked=1`) without the `changes` check — a concurrent request to the
  same session can slip through between the UPDATE and INSERT.
- Allowing the client to supply the new session ID during rotation — the server must always
  generate the new ID; client-supplied IDs are the definition of session fixation.
- Using predictable session IDs (sequential integers, timestamps) — IDs must be 256-bit random.

## Gotchas

- D1 `batch()` is transactional for writes but not fully ACID — in the event of a Worker crash
  between batch steps, D1 guarantees the batch either fully commits or does not; partial writes
  are not possible within a batch.
- `Set-Cookie` is silently ignored by React Native's `fetch()` when the request is made outside
  a WebView context — always return the new token in the response body for mobile clients.
- iOS Keychain and Android Keystore survive app reinstall on some versions — validate stored
  tokens against D1 on app resume, not just app launch.
- The `last_seen` UPDATE is fire-and-forget using `waitUntil` — it does not affect response
  latency but may lag by one request; do not rely on `last_seen` for real-time abuse detection.
- Moderator sessions have a 4h TTL — mobile apps that cache the session for longer will see
  sudden 401s; implement a session refresh flow before the TTL, not after.

## Verification

```bash
# 1. Confirm old session is revoked after email verification
OLD_TOKEN=$(curl -s https://api.example.com/session/start | jq -r .sessionToken)
NEW_TOKEN=$(curl -s -X POST https://api.example.com/verify-email \
  -H "Authorization: Bearer $OLD_TOKEN" \
  -d '{"token":"123456"}' | jq -r .sessionToken)
# Old token should now return 401
curl -s https://api.example.com/session \
  -H "Authorization: Bearer $OLD_TOKEN" | jq .error
# Expect: "SESSION_INVALID" or "Unauthorized"

# 2. New token works
curl -s https://api.example.com/session \
  -H "Authorization: Bearer $NEW_TOKEN" | jq .privilege
# Expect: "verified"

# 3. Concurrent rotation returns 409
# (two simultaneous POST /verify-email with same token)
curl -s -X POST https://api.example.com/verify-email \
  -H "Authorization: Bearer $OLD_TOKEN" -d '{"token":"123456"}' &
curl -s -X POST https://api.example.com/verify-email \
  -H "Authorization: Bearer $OLD_TOKEN" -d '{"token":"123456"}' &
wait
# One should return 200, the other 409 or 401

# 4. D1 audit — confirm rotated_from chain
wrangler d1 execute example project-db --command \
  "SELECT id, privilege, rotated_from, revoked FROM sessions ORDER BY created_at DESC LIMIT 10"
```

## Related

- `session-fixation-rotation.md`
- `session-cookies-vs-jwt.md`
- `jwt-storage-mobile-workers-auth.md`
- `anonymous-auth-jwt-mobile-storage.md`
- `oauth-pkce-mobile-cloudflare-workers.md`
- `race-condition-toctou-web.md`

## Sources

- OWASP Session Management: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP Session Fixation: https://owasp.org/www-community/attacks/Session_fixation
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- RFC 8471 Token Binding (historical): https://www.rfc-editor.org/rfc/rfc8471
- NIST SP 800-63B session management: https://pages.nist.gov/800-63-3/sp800-63b.html
