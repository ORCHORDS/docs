# session-management-workers

**Issue:** Stateless session management in Cloudflare Workers — cookie-based sessions backed by KV
**Date:** 2026-08-11
**Status:** documented

## Pattern

Sessions are stored in KV. Each session is a JSON object keyed by a random session ID
that lives in an HttpOnly cookie.

## Session shape

```typescript
interface Session {
  user_id: string;
  tenant_id: string;
  role: string;
  email: string;
  display_name: string;
  created_at: number;
  last_seen: number;
  ip: string;
  user_agent: string;
}
```

## Creating a session (after login)

```typescript
async function createSession(env: Env, data: Omit<Session, 'created_at' | 'last_seen'>): Promise<string> {
  const sessionId = crypto.randomUUID();
  const now = Math.floor(Date.now() / 1000);
  const session: Session = { ...data, created_at: now, last_seen: now };
  await env.SESSIONS!.put(`sess:${sessionId}`, JSON.stringify(session), {
    expirationTtl: 7 * 24 * 60 * 60,  // 7 days
  });
  return sessionId;
}

// In login handler:
const sessionId = await createSession(env, { user_id, tenant_id, role, email, display_name, ip, user_agent });
return new Response(JSON.stringify({ ok: true }), {
  status: 200,
  headers: {
    'content-type': 'application/json',
    'set-cookie': `sid=${sessionId}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${7 * 24 * 60 * 60}`,
  },
});
```

## Reading a session (authenticate())

```typescript
async function authenticate(request: Request, env: Env): Promise<McContext | null> {
  const cookieHeader = request.headers.get('cookie') ?? '';
  const sid = parseCookie(cookieHeader)['sid'];
  if (!sid) return null;

  const raw = await env.SESSIONS!.get(`sess:${sid}`);
  if (!raw) return null;

  let session: Session;
  try { session = JSON.parse(raw); } catch { return null; }

  // Rolling expiry — update last_seen on each request (fire-and-forget):
  const now = Math.floor(Date.now() / 1000);
  env.SESSIONS!.put(`sess:${sid}`, JSON.stringify({ ...session, last_seen: now }), {
    expirationTtl: 7 * 24 * 60 * 60,
  });  // intentionally not awaited — don't block the response

  return {
    user: {
      id: session.user_id,
      tenant_id: session.tenant_id,
      role: session.role as McUser['role'],
      email: session.email,
      display_name: session.display_name,
    },
    tenant: await getTenant(env, session.tenant_id),
    session: { id: sid },
    request_id: request.headers.get('cf-ray') ?? crypto.randomUUID(),
    ip: request.headers.get('cf-connecting-ip') ?? session.ip,
    user_agent: request.headers.get('user-agent') ?? session.user_agent,
  };
}

function parseCookie(header: string): Record<string, string> {
  return Object.fromEntries(
    header.split(';').map(c => c.trim().split('=').map(decodeURIComponent))
  );
}
```

## Destroying a session (logout)

```typescript
export const onRequestPost: PagesFunction<Env> = async (context) => {
  const cookieHeader = context.request.headers.get('cookie') ?? '';
  const sid = parseCookie(cookieHeader)['sid'];
  if (sid) await context.env.SESSIONS!.delete(`sess:${sid}`);
  return new Response(null, {
    status: 204,
    headers: { 'set-cookie': 'sid=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0' },
  });
};
```

## Force-logout all sessions for a user

When a user changes password or is disabled, invalidate all their sessions.
Since KV doesn't support scans by prefix efficiently, store a generation counter:

```typescript
// On password change:
await env.SESSIONS!.put(`sess:gen:${userId}`, String(Date.now()));

// In authenticate(), after reading session:
const gen = await env.SESSIONS!.get(`sess:gen:${session.user_id}`);
if (gen && Number(gen) > session.created_at * 1000) return null;  // session pre-dates gen → invalid
```

## Cookie security flags

| Flag | Value | Reason |
|------|-------|--------|
| `HttpOnly` | required | Prevents JS access — XSS-proof |
| `Secure` | required | HTTPS only |
| `SameSite` | `Lax` | Prevents CSRF on navigation; use `Strict` if no OAuth callbacks needed |
| `Path` | `/` | Scope to all paths |
| `Max-Age` | 7 days in seconds | Session lifetime |
| `Domain` | omit | Let browser default to exact host |

## Gotchas

- **KV write is async**: The rolling-expiry `put` in authenticate must NOT be awaited in the critical path — do it fire-and-forget. Workers have a `context.waitUntil()` API for this but it requires passing the execution context through.
- **Session size limit**: KV values max 25MB per value, but keep session JSON tiny (< 1KB). Don't store permissions or large objects — re-fetch from DB when needed.
- **No session scan**: KV doesn't support listing all sessions for a user. Use the generation counter pattern for force-logout, or store session IDs per user in a separate KV key.
- **Cookie parser**: `parseCookie` above fails if cookie values contain `=`. Use a proper parser for production or limit cookie values to URL-safe tokens.
- **CSRF**: `SameSite=Lax` prevents CSRF for most cases. For APIs called cross-origin, verify the `Origin` header.
- **SESSIONS binding**: Must be a KV namespace, not the same namespace as RATE_LIMIT or other KV uses — separate namespaces for operational clarity.

## Related

- `mccontext-gate-pattern.md`
- `kv-rate-limiting.md`
- `workers-types-migration.md`
- `timing-safe-compare.md`
- `typescript-route-handler.md`
