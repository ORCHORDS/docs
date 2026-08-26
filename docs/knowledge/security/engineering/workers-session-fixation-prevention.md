# Session Fixation and Hijacking Prevention with Cloudflare Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Users who complete a password change or MFA step still hold the same session token they had before the privilege change. An attacker who obtained the pre-authentication session ID can hijack the session post-login. Additionally, a user's session is not invalidated on password change, allowing a compromised session to remain valid indefinitely.

---

## Context

Session fixation (CWE-384) occurs when the server reuses a session identifier across an authentication state change. Cloudflare Workers, being stateless, must store session state in KV (or Durable Objects). The session cookie must be regenerated after:

1. Successful primary authentication (login).
2. MFA step-up verification.
3. Password or credential change.
4. Role/permission elevation.

Related threats:
- **Session hijacking**: an attacker obtains a valid session token via XSS, network sniffing, or log exposure.
- **Session riding (CSRF)**: cross-origin request forges an authenticated action.
- **Concurrent session abuse**: a leaked token allows a second active session.

This article focuses on Workers-side controls. Front-end CSP and CSRF tokens are covered separately.

---

## Solution

### KV Session Schema

```typescript
// src/types/session.ts
export interface SessionData {
  userId: string;
  email: string;
  authLevel: 'unauthenticated' | 'password' | 'mfa';
  createdAt: number;
  lastActivityAt: number;
  ipBinding: string;          // IP address at session creation
  fingerprintHash: string;    // hash of User-Agent + Accept-Language
  regeneratedAt?: number;     // last time the session ID was rotated
  invalidated?: boolean;
}

export const SESSION_TTL_SECONDS = 3600 * 8;   // 8 hours idle expiry
export const SESSION_COOKIE_NAME = '__Host-sid'; // __Host- prefix enforces Secure+path=/
```

### Session ID Generation

```typescript
// src/lib/session.ts
import type { SessionData } from '../types/session';

export const SESSION_COOKIE_NAME = '__Host-sid';
export const SESSION_TTL_SECONDS = 3600 * 8;

function generateSessionId(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}

function buildCookieHeader(sessionId: string, maxAge: number): string {
  // __Host- prefix requires: Secure, no Domain attribute, Path=/
  return [
    `${SESSION_COOKIE_NAME}=${sessionId}`,
    'HttpOnly',
    'Secure',
    'SameSite=Strict',
    `Path=/`,
    `Max-Age=${maxAge}`,
  ].join('; ');
}

async function fingerprintRequest(request: Request): Promise<string> {
  const ua = request.headers.get('User-Agent') ?? '';
  const lang = request.headers.get('Accept-Language') ?? '';
  const raw = `${ua}||${lang}`;
  const encoded = new TextEncoder().encode(raw);
  const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
  return Array.from(new Uint8Array(hashBuffer), b => b.toString(16).padStart(2, '0')).join('');
}

export async function createSession(
  request: Request,
  env: { SESSIONS: KVNamespace },
  userId: string,
  email: string,
  authLevel: SessionData['authLevel']
): Promise<{ sessionId: string; cookieHeader: string }> {
  const sessionId = generateSessionId();
  const clientIp = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  const fingerprintHash = await fingerprintRequest(request);

  const session: SessionData = {
    userId,
    email,
    authLevel,
    createdAt: Date.now(),
    lastActivityAt: Date.now(),
    ipBinding: clientIp,
    fingerprintHash,
  };

  await env.SESSIONS.put(
    `session:${sessionId}`,
    JSON.stringify(session),
    { expirationTtl: SESSION_TTL_SECONDS }
  );

  return { sessionId, cookieHeader: buildCookieHeader(sessionId, SESSION_TTL_SECONDS) };
}

export async function regenerateSession(
  request: Request,
  env: { SESSIONS: KVNamespace },
  oldSessionId: string,
  updates: Partial<Pick<SessionData, 'authLevel'>>
): Promise<{ sessionId: string; cookieHeader: string }> {
  const raw = await env.SESSIONS.get(`session:${oldSessionId}`);
  if (!raw) throw new Error('Session not found for regeneration');

  const existing: SessionData = JSON.parse(raw);

  // Invalidate the old session ID immediately
  await env.SESSIONS.delete(`session:${oldSessionId}`);

  const newSessionId = generateSessionId();
  const updated: SessionData = {
    ...existing,
    ...updates,
    lastActivityAt: Date.now(),
    regeneratedAt: Date.now(),
  };

  await env.SESSIONS.put(
    `session:${newSessionId}`,
    JSON.stringify(updated),
    { expirationTtl: SESSION_TTL_SECONDS }
  );

  return { sessionId: newSessionId, cookieHeader: buildCookieHeader(newSessionId, SESSION_TTL_SECONDS) };
}
```

### Session Validation Middleware

```typescript
// src/lib/validate-session.ts
import type { SessionData } from '../types/session';
import { SESSION_COOKIE_NAME } from './session';

interface Env {
  SESSIONS: KVNamespace;
}

function parseCookies(cookieHeader: string): Record<string, string> {
  return Object.fromEntries(
    cookieHeader.split(';').map(c => {
      const [k, ...rest] = c.trim().split('=');
      return [k.trim(), rest.join('=').trim()];
    })
  );
}

async function fingerprintRequest(request: Request): Promise<string> {
  const ua = request.headers.get('User-Agent') ?? '';
  const lang = request.headers.get('Accept-Language') ?? '';
  const raw = `${ua}||${lang}`;
  const encoded = new TextEncoder().encode(raw);
  const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
  return Array.from(new Uint8Array(hashBuffer), b => b.toString(16).padStart(2, '0')).join('');
}

export async function validateSession(
  request: Request,
  env: Env
): Promise<{ valid: false } | { valid: true; sessionId: string; session: SessionData }> {
  const cookieHeader = request.headers.get('Cookie') ?? '';
  const cookies = parseCookies(cookieHeader);
  const sessionId = cookies[SESSION_COOKIE_NAME];

  if (!sessionId) return { valid: false };

  const raw = await env.SESSIONS.get(`session:${sessionId}`);
  if (!raw) return { valid: false };

  const session: SessionData = JSON.parse(raw);

  // Check invalidation flag (e.g. set on password change)
  if (session.invalidated) return { valid: false };

  // IP binding check — optional, can be disabled for mobile users
  const clientIp = request.headers.get('CF-Connecting-IP') ?? 'unknown';
  if (session.ipBinding !== clientIp) {
    console.warn(JSON.stringify({
      event: 'session_ip_mismatch',
      sessionId: sessionId.slice(0, 8) + '...',
      expectedIp: session.ipBinding,
      actualIp: clientIp,
    }));
    // Log and allow for now; change to `return { valid: false }` for strict mode
  }

  // Fingerprint check
  const currentFingerprint = await fingerprintRequest(request);
  if (session.fingerprintHash !== currentFingerprint) {
    console.warn(JSON.stringify({
      event: 'session_fingerprint_mismatch',
      sessionId: sessionId.slice(0, 8) + '...',
    }));
    return { valid: false };
  }

  return { valid: true, sessionId, session };
}
```

### Session Invalidation on Password Change

```typescript
// src/handlers/change-password.ts
import { validateSession, regenerateSession } from '../lib/validate-session';

export async function handleChangePassword(
  request: Request,
  env: Env
): Promise<Response> {
  const sessionResult = await validateSession(request, env);
  if (!sessionResult.valid) {
    return new Response('Unauthorized', { status: 401 });
  }

  const { sessionId, session } = sessionResult;
  const body = await request.json<{ currentPassword: string; newPassword: string }>();

  // ... verify currentPassword against stored hash ...

  // Invalidate ALL sessions for this user, not just the current one
  await invalidateAllUserSessions(env, session.userId);

  // Issue a brand-new session post-password-change
  const { cookieHeader } = await createSession(
    request, env, session.userId, session.email, 'password'
  );

  return new Response(JSON.stringify({ ok: true }), {
    headers: {
      'Content-Type': 'application/json',
      'Set-Cookie': cookieHeader,
    },
  });
}

async function invalidateAllUserSessions(
  env: { SESSIONS: KVNamespace },
  userId: string
): Promise<void> {
  // List all sessions for this user via a secondary index key
  const indexKey = `user_sessions:${userId}`;
  const raw = await env.SESSIONS.get(indexKey);
  const sessionIds: string[] = raw ? JSON.parse(raw) : [];

  await Promise.all(
    sessionIds.map(id => env.SESSIONS.delete(`session:${id}`))
  );
  await env.SESSIONS.delete(indexKey);
}
```

### Concurrent Session Limit

```typescript
// src/lib/session.ts (extended createSession)
async function enforceSessionLimit(
  env: { SESSIONS: KVNamespace },
  userId: string,
  maxSessions = 3
): Promise<void> {
  const indexKey = `user_sessions:${userId}`;
  const raw = await env.SESSIONS.get(indexKey);
  let sessions: string[] = raw ? JSON.parse(raw) : [];

  // Prune expired/deleted sessions
  const alive = (
    await Promise.all(
      sessions.map(async id => {
        const exists = await env.SESSIONS.get(`session:${id}`);
        return exists ? id : null;
      })
    )
  ).filter((id): id is string => id !== null);

  if (alive.length >= maxSessions) {
    // Evict oldest (sessions are ordered by creation — evict head)
    const toEvict = alive.slice(0, alive.length - maxSessions + 1);
    await Promise.all(toEvict.map(id => env.SESSIONS.delete(`session:${id}`)));
    sessions = alive.slice(alive.length - maxSessions + 1);
  } else {
    sessions = alive;
  }

  await env.SESSIONS.put(indexKey, JSON.stringify(sessions), {
    expirationTtl: SESSION_TTL_SECONDS,
  });
}
```

---

## Implementation Details

- **`__Host-` cookie prefix**: Browsers enforce that cookies with this prefix must have `Secure`, no `Domain` attribute, and `Path=/`. This prevents subdomain-based session fixation attacks.
- **`SameSite=Strict`**: Prevents the cookie from being sent on cross-site requests, mitigating CSRF. Use `SameSite=Lax` only if cross-site GET navigation must carry the session.
- **KV secondary index**: The `user_sessions:{userId}` key allows invalidating all sessions without a KV list scan. Keep it updated atomically with session creation/deletion (using a Durable Object for true atomicity if needed).
- **Fingerprint binding**: UA + Accept-Language is a weak but low-friction signal. Do not use IP for fingerprinting alone — CGNATs and mobile networks change IPs frequently.
- **Idle vs. absolute expiry**: KV TTL handles idle expiry. For absolute expiry, store `createdAt` in the session and reject sessions older than 8 hours in `validateSession`.

---

## Anti-patterns

- **Reusing the session ID after login** — the entire point of session fixation attacks; always regenerate.
- **Storing sessions in a signed JWT without server-side revocation** — JWTs cannot be invalidated before expiry without a server-side revocation list.
- **Using `document.cookie` accessible cookies** — always set `HttpOnly` to prevent JavaScript from reading the session token.
- **Long-lived sessions** — sessions lasting more than 24 hours increase the window of opportunity for a hijacked token.
- **Not invalidating on password change** — a compromised session remains valid even after the user responds to an account takeover.

---

## Gotchas

- KV writes are eventually consistent. After `env.SESSIONS.delete(oldSessionId)`, a read from another edge node may still return the old session for up to ~60 s. For strict revocation, use Durable Objects.
- The concurrent session limit index (`user_sessions:{userId}`) must be maintained in sync with session creation/deletion. A bug that fails to update the index will either allow too many sessions or incorrectly evict valid sessions.
- `SameSite=Strict` breaks OAuth redirect flows where the IdP redirects back to your app — the cookie is not sent on the top-level navigation from the IdP. Downgrade to `SameSite=Lax` for the auth callback route only.

---

## Verification

```bash
# 1. Log in, capture session cookie
SESSION_BEFORE=$(curl -si -X POST https://api.example.com/login \
  -d '{"email":"test@test.com","password":"Test1234!"}' \
  | grep -i set-cookie | grep __Host-sid | awk '{print $2}')

# 2. Trigger MFA completion, verify new session ID issued
SESSION_AFTER=$(curl -si -X POST https://api.example.com/mfa/verify \
  -H "Cookie: $SESSION_BEFORE" \
  -d '{"code":"123456"}' \
  | grep -i set-cookie | grep __Host-sid | awk '{print $2}')

echo "Before: $SESSION_BEFORE"
echo "After:  $SESSION_AFTER"
[ "$SESSION_BEFORE" != "$SESSION_AFTER" ] && echo 'PASS: session regenerated' || echo 'FAIL'

# 3. Try old session — must return 401
curl -si -H "Cookie: $SESSION_BEFORE" https://api.example.com/api/profile | head -1

# 4. Change password — all sessions invalidated
curl -si -X POST https://api.example.com/account/change-password \
  -H "Cookie: $SESSION_AFTER" \
  -d '{"currentPassword":"Test1234!","newPassword":"NewPass567!"}'

# Old session after password change — must return 401
curl -si -H "Cookie: $SESSION_AFTER" https://api.example.com/api/profile | head -1
```

---

## Related

- `documentation/docs/policies/security/workers-oauth2-pkce-flow.md`
- `documentation/docs/policies/security/jwt-validation-workers.md`
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html

---

## Sources

- CWE-384: Session Fixation — https://cwe.mitre.org/data/definitions/384.html
- RFC 6265bis (Cookie Prefixes): https://httpwg.org/http-extensions/draft-ietf-httpbis-rfc6265bis.html
- Cloudflare KV consistency model: https://developers.cloudflare.com/kv/reference/how-kv-works/
