# Durable Objects WebSocket Hibernation Auth Persistence

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A real-time collaboration Worker uses Durable Objects (DO) to hold WebSocket connections. When the DO hibernates (evicted from memory to save CPU costs), it loses all in-memory state including the authenticated user identity that was validated at connection time. On wake, the DO re-accepts the socket from the hibernation API but has no record of who the socket belongs to, inadvertently treating re-awakened connections as unauthenticated or, worse, accepting messages without re-validating identity.

## Context

Cloudflare Durable Objects support WebSocket Hibernation: the runtime can evict a DO from memory between messages, serializing open WebSocket connections to disk. The DO's `webSocketMessage`, `webSocketClose`, and `webSocketError` handlers are called on a fresh object instance when traffic arrives. Any auth state stored in `this.` instance properties is gone after hibernation. The correct pattern attaches a serializable auth attachment to each WebSocket at the time of the upgrade (using `server.serializeAttachment()`), then reads it back in every handler before processing the message.

## 1. Attaching Auth Claims at Upgrade Time

Validate the token once — at the HTTP upgrade — and serialize the verified claims onto the socket. Never re-validate by re-reading a request header inside `webSocketMessage`, because there is no request at that point.

```typescript
import { DurableObject } from "cloudflare:workers";

interface AuthAttachment {
  userId: string;
  roles: string[];
  exp: number; // JWT expiry as Unix seconds
}

export class CollabRoom extends DurableObject {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (request.headers.get("Upgrade") !== "websocket") {
      return new Response("Expected WebSocket upgrade", { status: 426 });
    }

    // Validate JWT from the Upgrade request
    const token = url.searchParams.get("token");
    if (!token) return new Response("Missing token", { status: 401 });

    const claims = await verifyJwt(token, this.env.JWT_SECRET);
    if (!claims) return new Response("Invalid token", { status: 401 });

    const { 0: client, 1: server } = new WebSocketPair();

    // Serialize auth claims onto the socket — survives hibernation
    const attachment: AuthAttachment = {
      userId: claims.sub,
      roles: claims.roles ?? [],
      exp: claims.exp,
    };
    this.ctx.acceptWebSocket(server);
    server.serializeAttachment(attachment);

    return new Response(null, { status: 101, webSocket: client });
  }
```

## 2. Reading Auth Attachment in Message Handlers

```typescript
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    // Deserialize the auth attachment — this works after hibernation
    const auth = ws.deserializeAttachment() as AuthAttachment | null;
    if (!auth) {
      ws.close(4401, "Unauthenticated");
      return;
    }

    // Enforce token expiry even after hibernation
    if (Date.now() / 1000 > auth.exp) {
      ws.close(4401, "Session expired");
      return;
    }

    // Role-based action gating
    const event = JSON.parse(message as string);
    if (event.type === "admin:kick" && !auth.roles.includes("admin")) {
      ws.send(JSON.stringify({ error: "Forbidden" }));
      return;
    }

    await this.handleEvent(auth.userId, event);
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    const auth = ws.deserializeAttachment() as AuthAttachment | null;
    const userId = auth?.userId ?? "unknown";
    console.log(`WebSocket closed for user ${userId}: ${code} ${reason}`);
    await this.ctx.storage.delete(`presence:${userId}`);
  }
```

## 3. Presence Tracking Surviving Hibernation

Store presence in Durable Object storage (persistent across hibernation) rather than in `this.` instance properties:

```typescript
  private async handleEvent(userId: string, event: Record<string, unknown>): Promise<void> {
    if (event.type === "ping") {
      // Update last-seen timestamp in persistent storage
      await this.ctx.storage.put(`presence:${userId}`, Date.now());
      const sockets = this.ctx.getWebSockets();
      for (const ws of sockets) {
        const a = ws.deserializeAttachment() as AuthAttachment | null;
        if (a) ws.send(JSON.stringify({ type: "pong", userId }));
      }
    }
  }

  async alarm(): Promise<void> {
    // Evict stale presence records (users silent for > 5 minutes)
    const cutoff = Date.now() - 5 * 60 * 1000;
    const all = await this.ctx.storage.list<number>({ prefix: "presence:" });
    for (const [key, lastSeen] of all) {
      if (lastSeen < cutoff) await this.ctx.storage.delete(key);
    }
    // Reschedule alarm
    this.ctx.storage.setAlarm(Date.now() + 60_000);
  }
```

## 4. Re-issuing Tokens Without Forcing Re-connection

When a token nears expiry, push a refresh challenge over the open socket instead of closing it:

```typescript
  private async maybeRefreshToken(ws: WebSocket, auth: AuthAttachment): Promise<void> {
    const secondsRemaining = auth.exp - Date.now() / 1000;
    if (secondsRemaining < 300) {
      // Prompt the client to refresh within 5 minutes of expiry
      ws.send(JSON.stringify({ type: "token:refresh_required", expiresIn: secondsRemaining }));
    }
  }

  // Client sends: { type: "token:refresh", newToken: "..." }
  private async handleTokenRefresh(ws: WebSocket, newToken: string): Promise<void> {
    const claims = await verifyJwt(newToken, this.env.JWT_SECRET);
    if (!claims) {
      ws.close(4401, "Token refresh failed");
      return;
    }
    const newAttachment: AuthAttachment = {
      userId: claims.sub,
      roles: claims.roles ?? [],
      exp: claims.exp,
    };
    // Must be the same user — prevent session hijacking via token swap
    const current = ws.deserializeAttachment() as AuthAttachment;
    if (current.userId !== newAttachment.userId) {
      ws.close(4403, "User identity mismatch");
      return;
    }
    ws.serializeAttachment(newAttachment);
    ws.send(JSON.stringify({ type: "token:refreshed" }));
  }
```

## 5. Broadcasting Only to Authenticated Sockets

After hibernation wake, `ctx.getWebSockets()` returns all attached sockets. Filter by attachment before broadcasting sensitive data:

```typescript
  private broadcastToRole(role: string, payload: unknown): void {
    for (const ws of this.ctx.getWebSockets()) {
      const auth = ws.deserializeAttachment() as AuthAttachment | null;
      if (auth && auth.roles.includes(role) && Date.now() / 1000 < auth.exp) {
        ws.send(JSON.stringify(payload));
      }
    }
  }
```

## Anti-patterns

- Storing `userId` in `this.connectedUsers = new Map()` — lost on hibernation, causing `undefined` user identity after wake.
- Re-reading `request.headers.get("Authorization")` inside `webSocketMessage` — the request object does not exist after the upgrade.
- Skipping expiry checks inside message handlers because "the token was valid at connection time" — sessions can persist for hours across hibernation cycles.
- Using `ctx.waitUntil(verifyJwt(...))` at upgrade without awaiting the result before accepting the socket — a race condition allows unauthenticated sockets to attach before the check resolves.

## Gotchas

- `server.serializeAttachment()` must be called BEFORE `this.ctx.acceptWebSocket(server)` in some runtime versions; always call it immediately after creating the `WebSocketPair` and before the `acceptWebSocket` call to avoid ordering issues.
- The attachment is stored as JSON; do not put large objects (e.g., full user profile) in it — keep it to a handful of primitive fields.
- `ws.deserializeAttachment()` returns `null` if no attachment was ever set, not an empty object. Always null-check.
- Hibernation is triggered automatically by the runtime; you cannot force it or predict it. Treat every handler invocation as potentially running on a cold instance.
- `ctx.getWebSockets()` after hibernation wake includes ALL sockets for the DO, not just the one that triggered the wake. Iterating all of them for a single-user operation is a bug.

## Verification

```bash
# Simulate hibernation by deploying a DO with a forced eviction delay and reconnecting
# 1. Connect with a valid token
wscat -c "wss://collab.example.com/room/test?token=$JWT"
# 2. Wait 30 seconds (DO may hibernate under low load in staging)
# 3. Send a message — verify the DO still knows your userId without re-auth
echo '{"type":"ping"}' | wscat -c "wss://collab.example.com/room/test?token=$JWT"
# Expected: {"type":"pong","userId":"user-123"}

# 4. Use an expired token to verify expiry enforcement
EXPIRED_JWT=$(generate-expired-jwt.sh)
wscat -c "wss://collab.example.com/room/test?token=<redacted-secret>
# Expected: connection closed 4401
```

## Related

- `durable-objects-auth-patterns.md`
- `durable-objects-alarm-session-expiry-revocation.md`
- `websocket-security-authorization.md`
- `jwt-refresh-token-rotation-durable-objects.md`
- `server-sent-events-auth-workers.md`

## Sources

- Cloudflare DO WebSocket Hibernation API: https://developers.cloudflare.com/durable-objects/api/websockets/
- `serializeAttachment` / `deserializeAttachment`: https://developers.cloudflare.com/durable-objects/api/websockets/#serializeattachment
- OWASP WebSocket Security: https://owasp.org/www-project-web-security-testing-guide/v42/4-Web_Application_Security_Testing/11-Client-Side_Testing/10-Testing_WebSockets
