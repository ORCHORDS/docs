# ADR: Migrating Durable Objects to the WebSocket Hibernation API

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
A real-time collaboration feature built on Durable Objects kept 400–800 concurrent WebSocket connections
open per object during peak hours. Monthly Cloudflare bill for DO duration charges exceeded budget by 3×
because objects were kept alive — accumulating wall-clock duration — even when all connected clients
were idle.

## Context
The original implementation used the classic `state.acceptWebSocket()` pattern added in 2022 but did not
opt into the hibernation extension introduced in 2023. Hibernation allows the Workers runtime to evict
a DO from memory between messages without closing client WebSockets, so duration is only charged while
the object is actually executing JavaScript. For a chat room that receives a burst of messages then goes
silent for minutes at a time, this is the difference between charging for 60 minutes of wall-clock time
versus 2–3 seconds of actual CPU time.

The migration decision was non-trivial: hibernating objects lose all in-memory state on eviction, which
required auditing every field on the DO class and deciding what to persist to DO Storage versus
reconstruct on wake.

## Decision: Migrate to Hibernation API

The team accepted the migration cost after a week-long spike proved that all business-critical state
could be serialized to DO Storage within the 128 KB per-key limit. The non-persistent caches (user
cursor positions, typing indicators) were deemed acceptable to lose on eviction — clients would simply
re-broadcast on reconnect.

### Before: Classic WebSocket Accept

```typescript
// OLD — object stays live indefinitely
export class CollabRoom implements DurableObject {
  private sessions = new Map<WebSocket, SessionState>();

  async fetch(request: Request): Promise<Response> {
    const upgrade = request.headers.get("Upgrade");
    if (upgrade !== "websocket") return new Response("Expected WebSocket", { status: 426 });

    const [client, server] = Object.values(new WebSocketPair());
    server.accept(); // Classic accept — no hibernation
    server.addEventListener("message", (event) => this.handleMessage(server, event));
    server.addEventListener("close", () => this.sessions.delete(server));
    this.sessions.set(server, { userId: getUserId(request) });
    return new Response(null, { status: 101, webSocket: client });
  }

  private handleMessage(ws: WebSocket, event: MessageEvent) {
    // ... handle message ...
  }
}
```

### After: Hibernation API

```typescript
// NEW — object can be evicted between messages; duration charged only during execution
export class CollabRoom implements DurableObject {
  constructor(private state: DurableObjectState, private env: Env) {}

  async fetch(request: Request): Promise<Response> {
    const upgrade = request.headers.get("Upgrade");
    if (upgrade !== "websocket") return new Response("Expected WebSocket", { status: 426 });

    const [client, server] = Object.values(new WebSocketPair());
    // Use state.acceptWebSocket instead of server.accept()
    this.state.acceptWebSocket(server, [getUserId(request)]);
    return new Response(null, { status: 101, webSocket: client });
  }

  // Handler called by runtime after wake; replaces addEventListener("message")
  async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
    const [userId] = ws.getTags();
    const data = JSON.parse(typeof message === "string" ? message : new TextDecoder().decode(message));
    await this.handleEvent(userId, data, ws);
  }

  async webSocketClose(ws: WebSocket, code: number, reason: string): Promise<void> {
    const [userId] = ws.getTags();
    await this.removeParticipant(userId);
  }

  async webSocketError(ws: WebSocket, error: unknown): Promise<void> {
    console.error(JSON.stringify({ event: "ws_error", error: String(error) }));
  }
}
```

## State Persistence on Eviction

Any field the DO held in memory before hibernation is gone on eviction. A pre-migration audit
categorized every field:

| Field | Category | Persistence strategy |
|---|---|---|
| `participants` Map | Business-critical | DO Storage under `"participants"` key |
| `documentSnapshot` | Business-critical | DO Storage under `"doc:snapshot"` key |
| `cursorPositions` | Ephemeral hint | Reconstructed from client re-broadcast on reconnect |
| `typingIndicators` Set | Ephemeral hint | Discarded on eviction; clients re-send on reconnect |

Loading state on each wake:

```typescript
async webSocketMessage(ws: WebSocket, message: string | ArrayBuffer): Promise<void> {
  // State is loaded lazily on first message after a potential eviction
  const participants = await this.state.storage.get<Map<string, Participant>>("participants")
    ?? new Map();
  // ... handle message using participants ...
}
```

## Eviction Safety: Alarms

The hibernation API integrates with DO Alarms. A scheduled alarm persists a checkpoint to DO Storage
every 30 seconds while any WebSocket is open, ensuring recent state survives unexpected eviction during
a burst:

```typescript
async alarm(): Promise<void> {
  const sockets = this.state.getWebSockets();
  if (sockets.length > 0) {
    await this.persistSnapshot();
    // Re-arm alarm for next checkpoint
    await this.state.storage.setAlarm(Date.now() + 30_000);
  }
}
```

## Cost Impact

After migration to the hibernation API across all 1 200 active room objects:

- DO duration billing dropped by 87 % in the first billing cycle
- No measurable increase in client-visible latency (wake-up overhead ≤ 15 ms p99)
- Two edge cases required client-side reconnection logic: very long idle periods where Cloudflare
  reclaims the DO entirely, and alarm drift during high write contention on DO Storage

## Anti-patterns
- Storing large ephemeral caches in DO memory and expecting them to survive between messages
- Using `server.accept()` (classic) in new DO code when the hibernation API is available
- Assuming `webSocketClose` is always called — clients can disconnect without a clean close frame;
  always reconcile participant lists via the alarm checkpoint
- Persisting cursor positions or typing indicators to DO Storage — the write amplification is not worth
  the durability gain for ephemeral UX state

## Gotchas
- `ws.getTags()` is the only way to identify which user a WebSocket belongs to after an eviction; store
  all per-socket identity in tags at `acceptWebSocket` time
- `state.getWebSockets()` returns all live WebSockets including those in `CLOSING` state; filter by
  `ws.readyState === WebSocket.OPEN` before broadcasting
- The hibernation API requires the `durable_object_websocket_hibernation` compatibility flag in older
  account configurations; newer accounts have it by default
- DO Storage `get()` returns `undefined` for missing keys, not `null`; always provide a default value

## Verification
1. Run Miniflare locally with `@cloudflare/vitest-pool-workers` and assert that simulating an eviction
   (by calling `state.storage.deleteAll()` mid-test then re-sending a message) does not corrupt room
   state.
2. Deploy to a staging environment; use `wrangler tail` to confirm `webSocketMessage` invocations appear
   as separate requests (each one starting from cold DO state) when idling between sends.
3. Compare Cloudflare dashboard DO duration metrics for a 24-hour period before and after the migration.

## Related
- `durable-object-alarm-silent-failure-payment-reminders.md`
- `d1-write-contention-viral-event-postmortem.md`
- `cost-optimization-cloudflare-stack.md`
- `workers-testing-miniflare-vitest.md`

## Sources
- Cloudflare DO Hibernation API — https://developers.cloudflare.com/durable-objects/api/websockets/#websocket-hibernation-api
- Cloudflare DO Alarms — https://developers.cloudflare.com/durable-objects/api/alarms/
- WebSocketPair and tags — https://developers.cloudflare.com/durable-objects/api/websockets/
