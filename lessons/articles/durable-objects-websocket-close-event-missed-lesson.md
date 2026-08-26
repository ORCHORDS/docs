# Durable Objects WebSocket close Event Is Not Guaranteed — Presence Tracking Stayed Stale

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A collaborative editing feature powered by Durable Objects showed users as "online"
long after they had closed their browser tab or lost network connectivity. The
presence sidebar displayed 12–40 ghost users during every session. Support tickets
called it "the ghost bug."

---

## Context

Cloudflare Durable Objects support WebSockets in two modes:

1. **Legacy (non-hibernating)**: the DO stays fully alive in memory for the lifetime of
   every open socket. The `close` event on `WebSocket` fires reliably when either side
   closes the connection gracefully.
2. **Hibernation API** (`this.ctx.acceptWebSocket(ws)`): the DO is evicted from memory
   between messages to save costs. On hibernation, socket state is serialised. The
   `webSocketClose` lifecycle method fires when the runtime detects closure — but *not*
   when the client's TCP stack disappears without sending a FIN (hard crash, network
   drop, mobile OS kill).

The ghost-user bug had two distinct root causes:
- We were using the hibernation API but had not implemented a heartbeat, so TCP
  half-open connections were never detected.
- We had also missed that **`webSocketError`** must be handled; an unhandled error
  does not call `webSocketClose`.

---

## WebSocket Lifecycle in Durable Objects (Hibernation API)

```typescript
// src/presence-do.ts
import { DurableObject } from "cloudflare:workers";

interface Session {
  userId: string;
  lastPing: number;
}

export class PresenceDO extends DurableObject {
  private sessions = new Map<WebSocket, Session>();

  async fetch(request: Request): Promise<Response> {
    const upgradeHeader = request.headers.get("Upgrade");
    if (upgradeHeader !== "websocket") {
      return new Response("Expected WebSocket", { status: 426 });
    }

    const { 0: client, 1: server } = new WebSocketPair();

    // Hibernation API — DO may sleep between messages.
    this.ctx.acceptWebSocket(server);

    const userId = new URL(request.url).searchParams.get("userId") ?? "anon";
    // Attach metadata so we can recover session after hibernation.
    server.serializeAttachment({ userId, lastPing: Date.now() });

    this.sessions.set(server, { userId, lastPing: Date.now() });
    this.broadcastPresence();

    return new Response(null, { status: 101, webSocket: client });
  }

  // Called by the runtime when a message arrives (after waking from hibernation).
  webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): void {
    const attachment = ws.deserializeAttachment() as Session;

    if (message === "ping") {
      // Update lastPing in the serialised attachment so it survives hibernation.
      ws.serializeAttachment({ ...attachment, lastPing: Date.now() });
      ws.send("pong");
      return;
    }
    // handle other message types…
  }

  // Called when the client closes gracefully (FIN received).
  webSocketClose(ws: WebSocket, code: number, reason: string): void {
    this.removeSession(ws);
    this.broadcastPresence();
  }

  // Called when the runtime detects a protocol error or socket fault.
  // Without this handler, the socket stays in the sessions map forever.
  webSocketError(ws: WebSocket, error: unknown): void {
    console.error("WebSocket error", error);
    this.removeSession(ws);
    this.broadcastPresence();
  }

  private removeSession(ws: WebSocket): void {
    this.sessions.delete(ws);
    try {
      ws.close(1011, "server error");
    } catch {
      // already closed
    }
  }

  private broadcastPresence(): void {
    const online = [...this.sessions.values()].map((s) => s.userId);
    const payload = JSON.stringify({ type: "presence", online });
    for (const ws of this.ctx.getWebSockets()) {
      try {
        ws.send(payload);
      } catch {
        // socket may have closed between the map iteration and send
      }
    }
  }
}
```

---

## Heartbeat to Detect TCP Half-Open Connections

A graceful `close` will never fire for a client that hard-crashes or goes offline.
Use a server-side alarm to sweep stale sockets.

```typescript
// src/presence-do.ts (additions)
export class PresenceDO extends DurableObject {
  private static readonly PING_INTERVAL_MS = 15_000;
  private static readonly STALE_THRESHOLD_MS = 45_000;

  async fetch(request: Request): Promise<Response> {
    // … same as before …

    // Ensure the sweep alarm is scheduled.
    const current = await this.ctx.storage.getAlarm();
    if (current === null) {
      await this.ctx.storage.setAlarm(Date.now() + PresenceDO.PING_INTERVAL_MS);
    }

    return new Response(null, { status: 101, webSocket: client });
  }

  async alarm(): Promise<void> {
    const now = Date.now();
    const stale: WebSocket[] = [];

    for (const ws of this.ctx.getWebSockets()) {
      const attachment = ws.deserializeAttachment() as Session | null;
      if (!attachment) {
        stale.push(ws);
        continue;
      }

      if (now - attachment.lastPing > PresenceDO.STALE_THRESHOLD_MS) {
        stale.push(ws);
      } else {
        // Send a server-initiated ping.
        try {
          ws.send("ping");
        } catch {
          stale.push(ws);
        }
      }
    }

    for (const ws of stale) {
      this.removeSession(ws);
    }

    if (this.ctx.getWebSockets().length > 0) {
      // Reschedule only while sessions remain.
      await this.ctx.storage.setAlarm(now + PresenceDO.PING_INTERVAL_MS);
    }

    this.broadcastPresence();
  }
}
```

---

## Rebuilding Sessions After Hibernation

After the DO wakes from hibernation, `this.sessions` is an empty in-memory Map.
Recover it from `ctx.getWebSockets()` and their serialised attachments before any
logic that iterates sessions.

```typescript
  private ensureSessionsLoaded(): void {
    if (this.sessions.size > 0) return; // already populated this activation
    for (const ws of this.ctx.getWebSockets()) {
      const attachment = ws.deserializeAttachment() as Session | null;
      if (attachment) {
        this.sessions.set(ws, attachment);
      }
    }
  }
```

Call `this.ensureSessionsLoaded()` at the top of `webSocketMessage`,
`webSocketClose`, `webSocketError`, and `alarm`.

---

## Client-Side Reconnection

```typescript
// client/presence.ts
function connectPresence(roomId: string, userId: string): WebSocket {
  const url = `wss://example.com/presence/${roomId}?userId=${userId}`;
  const ws = new WebSocket(url);

  let pingInterval: ReturnType<typeof setInterval>;

  ws.addEventListener("open", () => {
    // Client pings every 10 s so the server can update lastPing.
    pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send("ping");
    }, 10_000);
  });

  ws.addEventListener("close", () => {
    clearInterval(pingInterval);
    // Exponential back-off reconnect omitted for brevity.
    setTimeout(() => connectPresence(roomId, userId), 2_000);
  });

  ws.addEventListener("error", () => {
    clearInterval(pingInterval);
  });

  return ws;
}
```

---

## Anti-patterns

- **Relying solely on `webSocketClose`** — TCP RST, browser tab kill, and mobile OS
  suspend will not trigger a FIN; the close handler never fires.
- **Not implementing `webSocketError`** — errors leave dangling socket entries in any
  in-memory map; the DO may accumulate dead sessions across hibernation cycles.
- **In-memory-only session tracking** — using a plain `Map<WebSocket, Session>` without
  `serializeAttachment` means session metadata is lost every time the DO hibernates.
- **Alarm without re-scheduling** — the alarm fires once. If you do not call
  `setAlarm` again inside `alarm()`, the sweep never repeats.

---

## Gotchas

- `ctx.getWebSockets()` returns all sockets the runtime considers open, including
  TCP half-open ones. The only way to confirm a socket is truly alive is to send
  a message and await a response within the stale threshold.
- **`serializeAttachment` is synchronous and per-socket** — it replaces the entire
  attachment object; merge your existing fields before writing.
- **DO eviction is not immediate** — the runtime may keep the DO alive for a short
  window after all sockets close. Do not rely on eviction as a cleanup mechanism.
- Hibernation API requires `durable_object_alarms` compatibility flag if you use
  alarms; the flag is on by default for `compatibility_date >= 2022-10-31`.

---

## Verification

```bash
# Confirm hibernation API is in use (not legacy acceptWebSocket on server directly):
grep -r "acceptWebSocket" src/

# Load test: kill the client process mid-session and watch server-side logs
# for `removeSession` within one STALE_THRESHOLD window (~45 s).

# Check alarm is registered after a connection:
npx wrangler tail --format pretty 2>&1 | grep "alarm\|removeSession\|stale"
```

---

## Related

- `durable-objects-websocket-hibernation-migration-adr.md`
- `durable-object-alarm-silent-failure-payment-reminders.md`
- `durable-objects-storage-quota-limit-incident.md`
- `connection-storms-on-failover-thundering-reconnects.md`

---

## Sources

- Cloudflare Durable Objects – WebSocket Hibernation API:
  https://developers.cloudflare.com/durable-objects/api/websockets/
- Internal incident #3017 (2026-04-22) — "Ghost users in collaborative editor"
- RFC 6455 §5.5.1 — Close frames and half-open TCP connections
