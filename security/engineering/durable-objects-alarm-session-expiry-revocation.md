# Durable Objects Alarm-Driven Session Expiry and Revocation

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

JWT-based sessions have a baked-in expiry but cannot be revoked before that time without a server-side blocklist. Server-rendered session cookies work well on single-server deployments but behave unpredictably when sessions are stored in Workers KV with eventual consistency — a revoked session may still pass validation on edge nodes that have a stale KV read. You need a session store that guarantees revocation is visible immediately on the next request, with automatic expiry that does not rely on a background cron job.

Durable Objects provide strongly consistent, single-writer storage with the `setAlarm()` API that wakes the object at a specific time. This combination enables session state that is both immediately revocable and automatically expired without an external cleanup process.

## Context

Cloudflare Durable Objects are globally unique objects identified by a stable name or ID. All reads and writes to an object's storage are strongly consistent within that object — there is no replication lag. Each object can schedule a single alarm via `this.ctx.storage.setAlarm(timestamp)`, which wakes the object and calls the `alarm()` handler at or after the scheduled time.

This makes Durable Objects well-suited for session management: one object per session (or per user-session namespace), with the alarm triggering automatic expiry cleanup. The tradeoff is cost and latency — Durable Objects incur per-request and compute-duration costs above KV, so this pattern is best reserved for high-value sessions (admin access, payment flows, OAuth device codes) where strong consistency justifies the overhead.

## Session Object Design

Each session is a Durable Object instance identified by a session ID. The object stores session metadata and schedules its own alarm for expiry.

```typescript
// src/SessionDO.ts

export interface SessionData {
  userId: string;
  scopes: string[];
  createdAt: number;
  expiresAt: number;
  revoked: boolean;
  revokedAt?: number;
  revocationReason?: string;
  metadata: Record<string, unknown>;
}

export class SessionDO implements DurableObject {
  constructor(
    private readonly ctx: DurableObjectState,
    private readonly env: Env
  ) {}

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    switch (url.pathname) {
      case "/create":
        return this.handleCreate(request);
      case "/validate":
        return this.handleValidate();
      case "/revoke":
        return this.handleRevoke(request);
      case "/refresh":
        return this.handleRefresh(request);
      default:
        return new Response("Not found", { status: 404 });
    }
  }

  private async handleCreate(request: Request): Promise<Response> {
    const body = await request.json<Omit<SessionData, "createdAt" | "revoked">>();
    const now = Date.now();

    const session: SessionData = {
      ...body,
      createdAt: now,
      revoked: false,
    };

    await this.ctx.storage.put("session", session);

    // Schedule alarm for session expiry
    await this.ctx.storage.setAlarm(session.expiresAt);

    return Response.json({ ok: true, expiresAt: session.expiresAt });
  }

  private async handleValidate(): Promise<Response> {
    const session = await this.ctx.storage.get<SessionData>("session");

    if (!session) {
      return Response.json({ valid: false, reason: "not_found" }, { status: 404 });
    }

    if (session.revoked) {
      return Response.json(
        { valid: false, reason: "revoked", revokedAt: session.revokedAt },
        { status: 401 }
      );
    }

    if (Date.now() >= session.expiresAt) {
      return Response.json({ valid: false, reason: "expired" }, { status: 401 });
    }

    return Response.json({
      valid: true,
      userId: session.userId,
      scopes: session.scopes,
      expiresAt: session.expiresAt,
      metadata: session.metadata,
    });
  }

  private async handleRevoke(request: Request): Promise<Response> {
    const body = await request.json<{ reason?: string }>().catch(() => ({}));
    const session = await this.ctx.storage.get<SessionData>("session");

    if (!session) {
      return Response.json({ ok: false, reason: "not_found" }, { status: 404 });
    }

    const updated: SessionData = {
      ...session,
      revoked: true,
      revokedAt: Date.now(),
      revocationReason: body.reason ?? "explicit_revocation",
    };

    await this.ctx.storage.put("session", updated);

    // Cancel the expiry alarm — no need to clean up, already revoked
    // Keep the alarm so the DO is eventually cleaned up
    // (alarm will still fire and delete storage)

    return Response.json({ ok: true });
  }

  private async handleRefresh(request: Request): Promise<Response> {
    const body = await request.json<{ newExpiresAt: number }>();
    const session = await this.ctx.storage.get<SessionData>("session");

    if (!session || session.revoked) {
      return Response.json({ ok: false, reason: "invalid" }, { status: 401 });
    }

    if (Date.now() >= session.expiresAt) {
      return Response.json({ ok: false, reason: "expired" }, { status: 401 });
    }

    const maxExtension = 30 * 24 * 60 * 60 * 1000; // 30 days
    if (body.newExpiresAt > Date.now() + maxExtension) {
      return Response.json({ ok: false, reason: "extension_too_long" }, { status: 400 });
    }

    const updated: SessionData = { ...session, expiresAt: body.newExpiresAt };
    await this.ctx.storage.put("session", updated);

    // Reschedule the alarm to the new expiry
    await this.ctx.storage.setAlarm(body.newExpiresAt);

    return Response.json({ ok: true, expiresAt: body.newExpiresAt });
  }

  // Called by the Durable Objects runtime at session.expiresAt
  async alarm(): Promise<void> {
    const session = await this.ctx.storage.get<SessionData>("session");

    if (!session) {
      // Already cleaned up
      return;
    }

    // Delete all storage — this allows the DO to be garbage collected
    await this.ctx.storage.deleteAll();

    // Optionally emit a Logpush event for audit purposes
    console.log(JSON.stringify({
      event: "session_expired",
      userId: session.userId,
      sessionCreatedAt: session.createdAt,
      expiresAt: session.expiresAt,
      revoked: session.revoked,
    }));
  }
}
```

## Worker Routing to Session Durable Objects

The entry-point Worker routes session operations to the correct DO instance using the session ID as the DO name.

```typescript
// src/index.ts

interface Env {
  SESSION_DO: DurableObjectNamespace;
  SESSION_SIGNING_SECRET: string; // HMAC key for session ID MAC
}

export { SessionDO } from "./SessionDO";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/session/")) {
      return handleSessionRoute(request, env, url);
    }

    // Protected route example
    if (url.pathname.startsWith("/api/")) {
      return handleProtectedRoute(request, env);
    }

    return new Response("Not found", { status: 404 });
  },
};

async function handleSessionRoute(
  request: Request,
  env: Env,
  url: URL
): Promise<Response> {
  const segments = url.pathname.split("/");
  // /session/{sessionId}/{action}
  const sessionId = segments[2];
  const action = segments[3];

  if (!sessionId || !action) {
    return new Response("Bad Request", { status: 400 });
  }

  // Validate session ID format (64 hex chars)
  if (!/^[0-9a-f]{64}$/.test(sessionId)) {
    return new Response("Invalid session ID", { status: 400 });
  }

  const stub = env.SESSION_DO.get(env.SESSION_DO.idFromName(sessionId));
  return stub.fetch(new Request(`https://do-internal/${action}`, {
    method: request.method,
    headers: request.headers,
    body: request.body,
  }));
}

async function handleProtectedRoute(
  request: Request,
  env: Env
): Promise<Response> {
  const authHeader = request.headers.get("Authorization");
  if (!authHeader?.startsWith("Bearer ")) {
    return new Response("Unauthorized", { status: 401 });
  }

  const sessionId = authHeader.slice(7);

  if (!/^[0-9a-f]{64}$/.test(sessionId)) {
    return new Response("Unauthorized", { status: 401 });
  }

  const stub = env.SESSION_DO.get(env.SESSION_DO.idFromName(sessionId));
  const validationResponse = await stub.fetch(
    new Request("https://do-internal/validate")
  );

  if (!validationResponse.ok) {
    return new Response("Unauthorized", { status: 401 });
  }

  const sessionData = await validationResponse.json<{
    userId: string;
    scopes: string[];
  }>();

  // Add validated identity to request context
  const enrichedHeaders = new Headers(request.headers);
  enrichedHeaders.set("X-User-Id", sessionData.userId);
  enrichedHeaders.set("X-Scopes", sessionData.scopes.join(","));

  // Continue to downstream handler
  return handleApiRequest(new Request(request, { headers: enrichedHeaders }), env);
}

async function handleApiRequest(request: Request, _env: Env): Promise<Response> {
  return Response.json({ message: "ok", userId: request.headers.get("X-User-Id") });
}
```

## Bulk Revocation (e.g., on Password Reset)

When a user resets their password, all their sessions must be revoked. Since session IDs are stored in D1 per user, iterate and revoke each.

```typescript
// src/bulk-revoke.ts

interface Env {
  SESSION_DO: DurableObjectNamespace;
  DB: D1Database;
}

export async function revokeAllUserSessions(
  userId: string,
  env: Env,
  reason: string
): Promise<{ revoked: number }> {
  // D1 stores a mapping of userId -> [sessionId]
  const { results } = await env.DB.prepare(
    `SELECT session_id FROM sessions WHERE user_id = ? AND active = 1`
  ).bind(userId).all<{ session_id: string }>();

  let revoked = 0;

  // Revoke in parallel batches of 10 to avoid DO request rate limits
  const batchSize = 10;
  for (let i = 0; i < results.length; i += batchSize) {
    const batch = results.slice(i, i + batchSize);
    await Promise.all(
      batch.map(async ({ session_id }) => {
        try {
          const stub = env.SESSION_DO.get(
            env.SESSION_DO.idFromName(session_id)
          );
          await stub.fetch(new Request("https://do-internal/revoke", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reason }),
          }));
          revoked++;
        } catch {
          // Log but don't throw — best-effort bulk revocation
          console.error(`Failed to revoke session ${session_id}`);
        }
      })
    );
  }

  // Mark all sessions inactive in D1
  await env.DB.prepare(
    `UPDATE sessions SET active = 0, revoked_at = unixepoch() WHERE user_id = ?`
  ).bind(userId).run();

  return { revoked };
}
```

## Anti-patterns

- Using Workers KV for session storage that requires immediate revocation — KV has eventual consistency, so revoked sessions may still pass for up to 60 seconds
- Storing session state only in a JWT with no server-side record — cannot revoke without a blocklist
- Not deleting DO storage in the `alarm()` handler — orphaned DOs accumulate storage costs indefinitely
- Setting alarm to `session.expiresAt + jitter` without bounding the maximum — an attacker-controlled expiry could schedule an alarm far in the future, keeping the DO alive
- Routing all user sessions through one DO per user — creates a hot spot; one DO per session scales better
- Not validating the session ID format before calling `idFromName()` — extremely long IDs can cause issues

## Gotchas

- Durable Objects alarms fire "at or after" the scheduled time — they are not real-time; under load, expect up to 30 seconds of delay
- A DO with no storage and no pending alarm may be garbage collected — if the `alarm()` handler fails to delete storage, the DO stays alive and incurs cost
- `ctx.storage.setAlarm()` replaces any existing alarm — calling it multiple times on refresh is correct and intentional; there is no addAlarm
- DO egress counts as a subrequest from the Worker; deeply nested DO chains can hit the subrequest limit (1,000 per request in Workers)
- `alarm()` runs in a separate isolate invocation from the `fetch()` handler — it cannot access module-scope state that was set during a request

## Verification

```bash
# 1. Create a session
SESSION=$(curl -s -X POST https://api.example.com/session/$(openssl rand -hex 32)/create \
  -H "Content-Type: application/json" \
  -d '{"userId":"u1","scopes":["read"],"expiresAt":'$(($(date +%s)*1000 + 60000))'}')

# 2. Validate the session
curl -s https://api.example.com/session/<SESSION_ID>/validate

# 3. Revoke the session
curl -s -X POST https://api.example.com/session/<SESSION_ID>/revoke \
  -H "Content-Type: application/json" \
  -d '{"reason":"test_revocation"}'

# 4. Validate again — must return 401 with reason: "revoked" immediately
curl -s https://api.example.com/session/<SESSION_ID>/validate

# 5. Create a session with 5-second expiry and wait for alarm to fire
# Validate after 10 seconds — must return 404 (storage deleted)
```

## Related

- `jwt-refresh-token-rotation-durable-objects.md` — refresh token rotation using DOs
- `session-fixation-workers-d1-rotation.md` — session ID rotation on privilege change
- `rate-limiting-sliding-window-durable-objects.md` — using DO alarms for window resets
- `durable-objects-auth-patterns.md` — general auth patterns with Durable Objects

## Sources

- Cloudflare Durable Objects Alarms documentation — https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare Durable Objects Storage API — https://developers.cloudflare.com/durable-objects/api/storage-api/
- OWASP Session Management Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
