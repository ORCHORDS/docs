# Durable Objects for Low-Latency Stateful Coordination

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You have a feature requiring shared mutable state — a real-time seat reservation map, a rate limiter with per-user counters, a multiplayer collaborative editor, or a live inventory counter — and the naive approaches each fail in production: a Redis single node adds 30–80 ms cross-region round-trips, a D1 write lock serialises at the database and creates a hot partition, and KV's eventual consistency causes oversold inventory on flash sales.  You need strongly consistent, low-latency stateful operations that remain close to the mobile user without managing WebSocket servers.

## Context

**Durable Objects (DOs)** are single-threaded JavaScript classes that Cloudflare pins to exactly one CF PoP worldwide per DO instance.  All requests routed to that DO instance execute serially — no race conditions, no distributed locks needed.  State is persisted via the Durable Object Storage API (SQLite-backed, synchronous-write semantics).

The latency model:
- Request originates at PoP A (near the user), DO lives at PoP B (wherever Cloudflare pinned it).
- Round-trip A → B: 5–40 ms within the same region, 80–200 ms cross-region.
- For **WebSocket** connections: the WebSocket is held at PoP B (DO's PoP) for the lifetime of the session.  Mobile users connect once, pay the initial RTT cost, then get sub-millisecond in-DO state updates.

Mobile vs desktop: on cellular with high base RTT (60–120 ms), a single stateful operation via a traditional REST + DB path costs 2–4 RTTs (DNS, TLS, request, DB write) = 250–500 ms.  A DO WebSocket path pays 1 RTT for initial connection then 0 ms per subsequent in-session state mutation.  This is transformative for mobile live-update UIs.

## Section 1 — DO Basics and Storage API

```javascript
// src/ReservationDO.js
export class ReservationDO {
  constructor(state, env) {
    this.state = state;
    this.env   = env;
    // Block concurrent requests until constructor body completes
    this.state.blockConcurrencyWhile(async () => {
      this.seats = await this.state.storage.get('seats') ?? {};
    });
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === '/reserve') {
      return this.handleReserve(request);
    }
    if (url.pathname === '/ws') {
      return this.handleWebSocket(request);
    }
    return new Response('Not found', { status: 404 });
  }

  async handleReserve(request) {
    const { seatId, userId } = await request.json();

    if (this.seats[seatId]) {
      return Response.json({ ok: false, reason: 'already_taken' }, { status: 409 });
    }

    this.seats[seatId] = { userId, ts: Date.now() };
    // storage.put is synchronous within the single-threaded DO —
    // the write is durable before this promise resolves
    await this.state.storage.put('seats', this.seats);

    return Response.json({ ok: true, seatId });
  }
}
```

`wrangler.toml`:
```toml
[[durable_objects.bindings]]
name       = "RESERVATION_DO"
class_name = "ReservationDO"

[[migrations]]
tag  = "v1"
new_classes = ["ReservationDO"]
```

The calling Worker routes requests:

```javascript
// src/index.js
export { ReservationDO } from './ReservationDO.js';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/event/')) {
      const eventId = url.pathname.split('/')[2];
      // DO ID is derived from eventId — same eventId → same DO instance
      const id  = env.RESERVATION_DO.idFromName(eventId);
      const obj = env.RESERVATION_DO.get(id);
      return obj.fetch(request);
    }
    return new Response('Not found', { status: 404 });
  },
};
```

## Section 2 — WebSocket Hibernation for Mobile Connection Drops

Mobile connections drop frequently (tunnel, elevator, background tab throttling).  Without hibernation, a dropped WebSocket socket leaks the DO's memory until GC.  With **WebSocket Hibernation**, Cloudflare evicts the DO from memory between WebSocket messages, billing only for actual compute.

```javascript
export class LiveInventoryDO {
  constructor(state, env) {
    this.state    = state;
    this.sessions = new Set(); // WebSocket handles
    this.state.blockConcurrencyWhile(async () => {
      this.stock = await this.state.storage.get('stock') ?? 0;
    });
  }

  async fetch(request) {
    if (request.headers.get('Upgrade') !== 'websocket') {
      return new Response('Expected WebSocket', { status: 426 });
    }

    const [client, server] = Object.values(new WebSocketPair());

    // Accept with hibernation tag so the DO can be evicted between messages
    this.state.acceptWebSocket(server, ['inventory']);

    return new Response(null, { status: 101, webSocket: client });
  }

  // Called by the runtime when a message arrives (DO wakes from hibernation)
  async webSocketMessage(ws, message) {
    const { action, qty } = JSON.parse(message);

    if (action === 'decrement') {
      if (this.stock < qty) {
        ws.send(JSON.stringify({ error: 'insufficient_stock' }));
        return;
      }
      this.stock -= qty;
      await this.state.storage.put('stock', this.stock);
      // Broadcast new stock level to all connected clients
      for (const session of this.state.getWebSockets('inventory')) {
        session.send(JSON.stringify({ stock: this.stock }));
      }
    }
  }

  async webSocketClose(ws, code, reason) {
    ws.close(code, reason);
  }
}
```

With hibernation, the DO is billed only for the CPU time during `webSocketMessage` execution, not for idle WebSocket hold time.  A mobile user holding an open WebSocket for 10 minutes to watch live inventory costs ~0 ms of CPU billing between their own actions.

## Section 3 — DO Placement and Latency Minimization

By default, Cloudflare pins a new DO instance at the PoP nearest to the first request.  For global events (flash sale, live streaming), this means users in Australia may hit a DO pinned in London.

**Jurisdiction hints** (beta — available on paid plans) allow explicit region pinning:

```javascript
// Route APAC users to an APAC-pinned DO
const jurisdiction = getJurisdiction(request.cf.continent);
const id = env.SALE_DO.idFromName(`sale-2026-${jurisdiction}`);
```

**Location hints** for new instances:

```javascript
// Pin this DO instance close to EU users
const id = env.SALE_DO.idFromName('summer-sale');
const obj = env.SALE_DO.get(id, { locationHint: 'eeur' });
```

Valid `locationHint` values: `wnam`, `enam`, `sam`, `weur`, `eeur`, `apac`, `oc`, `afr`, `me`.

Practical latency table (P50, mobile LTE):

| User location | DO location | P50 RTT to DO |
|---------------|-------------|---------------|
| London | London (eeur) | 8 ms |
| Lagos | London (eeur) | 85 ms |
| Singapore | Singapore (apac) | 12 ms |
| Singapore | London (eeur) | 175 ms |
| Los Angeles | San Jose (wnam) | 15 ms |

**Conclusion:** for globally distributed flash sales with strict consistency, shard by region (`idFromName('sale-US')`, `idFromName('sale-EU')`) and accept that you need application-level reconciliation for cross-region inventory.

## Section 4 — DO SQLite Storage for Complex Queries

The `storage.sql` API (2025+) exposes a full SQLite instance per DO.  This is preferable over the key-value `storage.get/put` API when you need multi-column indexes or aggregate queries within a single DO.

```javascript
export class CartDO {
  constructor(state, env) {
    this.sql = state.storage.sql;
    this.state.blockConcurrencyWhile(async () => {
      this.sql.exec(`
        CREATE TABLE IF NOT EXISTS items (
          sku      TEXT PRIMARY KEY,
          qty      INTEGER NOT NULL,
          price_p  INTEGER NOT NULL,  -- price in pence/cents
          added_at INTEGER NOT NULL
        )
      `);
    });
  }

  async fetch(request) {
    const { method } = request;
    const url = new URL(request.url);

    if (method === 'POST' && url.pathname === '/add') {
      const { sku, qty, price_p } = await request.json();
      this.sql.exec(
        `INSERT INTO items (sku, qty, price_p, added_at)
         VALUES (?, ?, ?, ?)
         ON CONFLICT(sku) DO UPDATE SET qty = qty + excluded.qty`,
        sku, qty, price_p, Date.now()
      );
      return Response.json({ ok: true });
    }

    if (method === 'GET' && url.pathname === '/total') {
      const result = this.sql.exec(
        `SELECT SUM(qty * price_p) AS total_p FROM items`
      ).one();
      return Response.json({ total_p: result.total_p });
    }
  }
}
```

The SQLite API executes synchronously (no await) within the single-threaded DO.  There is no connection pool, no query planner cold-start, no network hop to a database — the storage is co-located with the compute.  P50 read latency for simple indexed queries: < 1 ms.

## Anti-patterns

- **One DO per user** — DO instances have a per-account limit.  Use one DO per shared resource (event, cart session, room) not per user.  Session state per user belongs in KV or a signed cookie.
- **Awaiting storage inside a tight loop** — `storage.put` inside a loop serialises writes.  Batch writes: collect all mutations, then call `storage.put(map)` once with a Map argument.
- **Storing large blobs in DO storage** — DO storage is capped at 128 KB per value.  Large assets (images, PDFs) must go to R2; store only the R2 key in the DO.
- **No `blockConcurrencyWhile` for initialization** — without it, concurrent requests race to read uninitialized state.  Always use `blockConcurrencyWhile` to load state in the constructor.
- **Ignoring WebSocket close events** — unreachable clients that never sent close frames keep the WebSocket reference alive.  Always handle `webSocketClose` and `webSocketError`.

## Gotchas

- DO CPU time limit is 30 s per request (not 10 ms like standard Workers).  But the wall-clock limit is still 30 s — long `sleep()` in a DO counts as wall-clock time, not CPU time.
- `idFromName` is deterministic and global — the same string always resolves to the same DO.  If you derive IDs from user-supplied input, validate/hash the input first to prevent enumeration attacks.
- The DO SQLite `exec` API is available only in Workers runtime v3 (2025+).  Older workers on `compatibility_date` before 2025-01-01 must use the KV-style `get/put` API.
- `locationHint` is a hint, not a guarantee.  Cloudflare may move a DO if capacity in the hinted region is exhausted.

## Verification

1. Deploy the reservation DO.  Send two concurrent POST `/reserve` requests for the same seat from different origins simultaneously.  Exactly one should succeed, one should receive 409 — proving serial execution without application-level locks.
2. Open a WebSocket to the LiveInventory DO from a mobile Chrome DevTools device-emulated session.  Drop the network in DevTools, wait 30 s, restore.  The WebSocket should reconnect and the DO should resume from hibernation with correct stock state.
3. Run `wrangler d1 execute --binding` is not applicable here — check DO storage via `wrangler durable-objects --list` and confirm the instance is pinned at the expected PoP.

## Related

- `cloudflare-workers-performance.md` — Worker CPU model
- `workers-cpu-time-optimization.md` — keeping compute within budget
- `kv-read-performance.md` — when KV is the right tool instead
- `d1-query-optimization.md` — D1 for multi-tenant relational data
- `websocket-sse-transport-performance.md` — WebSocket vs SSE transport choice

## Sources

- Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- WebSocket Hibernation API: https://developers.cloudflare.com/durable-objects/api/websockets/
- DO Storage SQLite API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- DO location hints: https://developers.cloudflare.com/durable-objects/reference/data-location/
