# DO WebSocket Hibernation API — Mobile Reconnect Patterns

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

example project anonymous-room clients on mobile lose messages after
reconnect, and presence flaps online/offline on every radio
handoff. DO Duration costs are higher than expected because
the standard WebSocket API keeps the DO pinned in memory even
when no messages are flowing.

## Context

Cloudflare Durable Objects have two WebSocket modes. Standard
mode (`server.accept()`) keeps the DO alive and billing Duration
(GB-s) for the lifetime of every open socket. The Hibernation
API (`ctx.acceptWebSocket()`) lets the DO sleep between events —
the Cloudflare edge maintains the socket while the DO process
is evicted, and Duration billing stops until the next message.
For a social app with sparse bursts, hibernation cuts Duration
costs dramatically. Mobile churn (radio RRC transitions, carrier
NAT expiry ≈ 30-120s, screen lock, WiFi-to-LTE handoff) means
clients reconnect every few minutes; the server-side session must
outlive any one socket.

## Hibernation API vs Standard WebSocket

```
                Standard (server.accept())
Duration bill:  Continuous while any socket is open
Routing:        addEventListener('message', handler)
Socket list:    Not runtime-managed; must maintain own Map

                Hibernation (ctx.acceptWebSocket())
Duration bill:  Only during event handling — zero at rest
Routing:        webSocketMessage() / webSocketClose() /
                webSocketError() class methods
Socket list:    ctx.getWebSockets([tag]) — survives hibernation
```

The two APIs are mutually exclusive per socket; mixing them on
the same socket throws at runtime.

## `acceptWebSocket()` and Hook Methods

```typescript
export class Room extends DurableObject {
  async fetch(request: Request): Promise<Response> {
    const url   = new URL(request.url);
    const token = url.searchParams.get('token') ?? '';
    const userId = await this.validateToken(token);
    if (!userId) return new Response('Unauthorized', {status:401});

    const lastSeq = Number(url.searchParams.get('last_seq') ?? 0);
    const [client, server] = Object.values(new WebSocketPair());

    // ctx.acceptWebSocket — NOT server.accept() — enables hibernation
    this.ctx.acceptWebSocket(server, [userId, 'room']);
    // Attach resume data to the socket; max 2048 bytes
    server.serializeAttachment({ userId, lastSeq });

    await this.replayMissed(server, lastSeq);
    return new Response(null, { status: 101, webSocket: client });
  }

  async webSocketMessage(ws: WebSocket, raw: string | ArrayBuffer) {
    const { userId } = ws.deserializeAttachment() as {
      userId: string; lastSeq: number;
    };
    const msg = JSON.parse(
      typeof raw === 'string' ? raw : new TextDecoder().decode(raw)
    );
    if (msg.type === 'post') await this.broadcast(userId, msg.body);
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string) {
    ws.close(code, reason); // complete the close handshake
    const { userId } = ws.deserializeAttachment() as any;
    await this.ctx.storage.put(`disconnect:${userId}`, Date.now());
    await this.ctx.storage.setAlarm(Date.now() + 60_000);
  }

  async webSocketError(ws: WebSocket, _error: unknown) {
    ws.close(1011, 'Internal error');
  }
}
```

## Serializing Pending Messages and Replay on Reconnect

Write messages to storage before broadcasting. A DO crash
between the two leaves a replayable record; the client's next
connect with `last_seq` triggers `replayMissed`.

```typescript
private async broadcast(fromId: string, body: string) {
  // 1. Durably store BEFORE sending (write-before-broadcast)
  const seq = ((await this.ctx.storage.get<number>('seq'))??0) + 1;
  await this.ctx.storage.put('seq', seq);
  await this.ctx.storage.put(`msg:${seq}`, body);

  const payload = JSON.stringify({ type:'message', seq, body });
  for (const peer of this.ctx.getWebSockets('room')) {
    if (peer.readyState === WebSocket.OPEN) peer.send(payload);
  }
}

private async replayMissed(ws: WebSocket, fromSeq: number) {
  const cur = (await this.ctx.storage.get<number>('seq')) ?? 0;
  for (let s = fromSeq + 1; s <= cur; s++) {
    const body = await this.ctx.storage.get<string>(`msg:${s}`);
    if (body) ws.send(JSON.stringify({type:'replay', seq:s, body}));
  }
}
```

Compact the replay buffer with a periodic alarm: delete
`msg:<seq>` entries older than 10 minutes to bound storage.

## Mobile Reconnect Loop with Exponential Backoff

```typescript
class RoomSocket {
  private attempt = 0;
  private lastSeq = 0;

  connect() {
    const url = `wss://ws.example.com/room/${this.roomId}` +
      `?token=<redacted-secret>&last_seq=${this.lastSeq}`;
    const ws = new WebSocket(url);
    ws.onopen    = () => { this.attempt = 0; this.heartbeat(ws); };
    ws.onclose   = () => this.schedule();
    ws.onerror   = () => this.schedule();
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.seq != null) this.lastSeq = m.seq;
    };
  }

  schedule(immediate = false) {
    if (immediate) { this.attempt = 0; return void this.connect(); }
    const cap = Math.min(30_000, 1_000 * 2 ** this.attempt++);
    setTimeout(() => this.connect(), Math.random() * cap); // jitter
  }

  heartbeat(ws: WebSocket) {
    // 25s: beats CF ~100s proxy timeout and cellular NAT floors
    setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('{"type":"ping"}');
    }, 25_000);
  }
}

// Reconnect immediately on foreground / network-back — no backoff
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') socket.schedule(true);
});
window.addEventListener('online',   () => socket.schedule(true));
window.addEventListener('pagehide', () => ws.close(1000,'pagehide'));
```

## Presence Detection Tolerating Mobile Interruptions

Never mark a user offline on raw socket close. NAT drops and
iOS tab freezes often produce no `close` event at all. Use a DO
alarm as a grace window:

```typescript
async alarm() {
  const entries = await this.ctx.storage.list<number>(
    { prefix: 'disconnect:' }
  );
  for (const [key, ts] of entries) {
    if (Date.now() - ts < 60_000) continue;
    const userId = key.replace('disconnect:', '');
    const live   = this.ctx.getWebSockets(userId);
    if (live.length === 0) {
      await this.broadcastPresence(userId, 'offline');
    }
    await this.ctx.storage.delete(key);
  }
}
```

A reconnect within 60s calls `acceptWebSocket` again; the alarm
finds `getWebSockets(userId).length > 0` and skips the broadcast.
For anonymous example project rooms, use a stable guest token as the
userId so the same identity persists across reconnects.

## Anti-patterns

- **`server.accept()` instead of `ctx.acceptWebSocket()`** —
  the DO stays pinned in memory; hibernation never engages.
- **Per-socket state in a class-field Map** — the Map is gone
  after hibernation; use `serializeAttachment` or `ctx.storage`.
- **Presence tied 1:1 to socket `close`** — mobile drops are
  silent; `close` often never fires. Require the grace alarm.
- **Unjittered reconnects** — a tower outage disconnects hundreds
  of clients simultaneously; synchronized retries stampede the DO.
- **Unbounded replay buffer** — every `msg:<seq>` entry in storage
  grows forever; add compaction or cap at a fixed window.

## Gotchas

- `serializeAttachment` cap is 2048 bytes; store only the resume
  cursor (userId, lastSeq), not message content.
- `ctx.getWebSockets()` includes CLOSING sockets; guard every
  `send` with `readyState === WebSocket.OPEN`.
- `webSocketClose` fires only for clean closes; unclean NAT drops
  produce `webSocketError` or silence — handle both paths.
- `ctx.acceptWebSocket()` must be called synchronously inside
  `fetch()`; deferring it to a `.then()` throws at runtime.
- Tags passed to `acceptWebSocket` must be strings; numbers
  coerce silently in some runtime versions, cause bugs in others.

## Verification

- `acceptWebSocket()` is called synchronously in `fetch()`; hooks
  are class methods, not `addEventListener` calls.
- `serializeAttachment({ userId, lastSeq })` called immediately
  after accept; deserialized in every hook method.
- Reconnect URL carries `last_seq`; server replays from
  `last_seq + 1` to current `seq` on each new connect.
- Client pings every 25s; closes and reconnects if no pong within
  5s; foreground/`online` events reconnect immediately (attempt=0).
- Presence offline is broadcast only inside the alarm handler
  after 60s, only when `getWebSockets(userId).length === 0`.
- Replay buffer compaction keeps storage below growth bounds.

## Related

- `documentation/docs/policies/cloudflare/durable-objects-websocket-hibernation.md`
- `documentation/docs/policies/cloudflare/websocket-mobile-radio-churn-reconnection.md`
- `documentation/docs/policies/cloudflare/durable-objects-alarms.md`
- `documentation/docs/policies/cloudflare/workers-websocket-upgrade.md`
- `documentation/docs/policies/mobile/react-native-netinfo.md`

## Source URLs (verified 2026-08-17)

- CF DO Use WebSockets (Hibernation API reference) —
  https://developers.cloudflare.com/durable-objects/best-practices/websockets/
- CF DO WebSocket Hibernation server example —
  https://developers.cloudflare.com/durable-objects/examples/websocket-hibernation-server
- CF DO what are Durable Objects (hibernation cost model) —
  https://developers.cloudflare.com/durable-objects/concepts/what-are-durable-objects/
- CF DO Pricing (Duration billing, hibernation savings) —
  https://developers.cloudflare.com/durable-objects/platform/pricing
- CF DO Rules (getWebSockets, serializeAttachment, tags) —
  https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/
