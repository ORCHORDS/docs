# Memory Usage Optimization in Durable Objects

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A Durable Object serving a collaborative document editor accumulates participant state and document history until the instance is evicted, but under sustained load the Worker logs begin showing `Error: Durable Object exceeded memory limit`.  A chat room DO holds message history in an in-memory array that grows unboundedly as the room fills.  A game state DO stores player coordinates in a plain JavaScript object that never prunes stale players who disconnected hours ago.  All of these are **unbounded in-memory growth** problems specific to the Durable Object execution model, where an instance can live for hours or days without eviction.

## Context

Durable Objects run as single-threaded JavaScript isolates.  Unlike standard Workers (which are typically short-lived), a DO instance may remain in memory for **minutes to hours**, accumulating state between requests.  Cloudflare enforces a **128 MB memory limit per DO instance** (as of 2025).  Exceeding it causes the instance to be terminated with an error, losing any in-memory state not persisted to storage.

Key memory model differences vs standard Workers:

| Dimension | Standard Worker | Durable Object |
|-----------|----------------|----------------|
| Typical lifespan | Milliseconds–seconds | Minutes–hours |
| In-memory accumulation risk | Low (short-lived) | High (long-lived) |
| Memory limit | 128 MB | 128 MB |
| State persistence | None (request-scoped) | Durable storage (SQLite/KV) |
| Eviction trigger | Request end | Inactivity or memory pressure |

The root cause of most DO memory problems is treating in-memory JavaScript structures as unbounded caches without eviction policies, instead of as working-set views over the durable storage layer.

## Section 1 — Auditing In-Memory Structures

The first step is identifying which in-memory structures grow over time.  Common offenders:

```javascript
// BAD — unbounded message history in memory
export class ChatRoomDO {
  constructor(state, env) {
    this.messages = [];   // grows forever as long as the DO lives
    this.sessions = new Map();
  }

  async handleMessage(userId, text) {
    this.messages.push({ userId, text, ts: Date.now() });  // never pruned
    // broadcast ...
  }
}
```

Audit pattern — add a memory diagnostic endpoint to your DO during development:

```javascript
export class ChatRoomDO {
  constructor(state, env) {
    this.state    = state;
    this.messages = [];
    this.sessions = new Map();
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === '/_diag/memory') {
      // Rough size estimation via JSON serialization
      const msgBytes     = JSON.stringify(this.messages).length;
      const sessionBytes = JSON.stringify([...this.sessions.entries()]).length;

      return Response.json({
        messagesCount:  this.messages.length,
        sessionsCount:  this.sessions.size,
        estMsgBytes:    msgBytes,
        estSessionBytes: sessionBytes,
        // V8 heap is not directly accessible in Workers, but JSON size is a proxy
      });
    }

    // ... rest of handler
  }
}
```

Call `/_diag/memory` under load to baseline which structures are growing before applying fixes.

## Section 2 — Bounded In-Memory Caches with Sliding Windows

Replace unbounded arrays with **size-capped circular buffers** and prune Maps by timestamp:

```javascript
// src/bounded-cache.js

/**
 * A fixed-capacity ring buffer for recent messages.
 * Overwrites oldest entries when full — no unbounded growth.
 */
export class RingBuffer {
  constructor(capacity) {
    this.buf  = new Array(capacity);
    this.cap  = capacity;
    this.head = 0;   // next write position
    this.size = 0;   // current element count
  }

  push(item) {
    this.buf[this.head] = item;
    this.head = (this.head + 1) % this.cap;
    if (this.size < this.cap) this.size++;
  }

  toArray() {
    if (this.size < this.cap) return this.buf.slice(0, this.size);
    // Unwrap the ring to chronological order
    return [
      ...this.buf.slice(this.head),
      ...this.buf.slice(0, this.head),
    ];
  }

  get length() { return this.size; }
}
```

```javascript
// src/ChatRoomDO.js
import { RingBuffer } from './bounded-cache.js';

const MAX_MESSAGES_IN_MEMORY = 200;
const SESSION_IDLE_EVICT_MS  = 10 * 60 * 1000;  // 10 minutes

export class ChatRoomDO {
  constructor(state, env) {
    this.state    = state;
    this.env      = env;
    // Cap message history in memory — older messages live in SQLite storage
    this.recent   = new RingBuffer(MAX_MESSAGES_IN_MEMORY);
    this.sessions = new Map();  // sessionId → { ws, userId, lastSeen }

    // Schedule periodic cleanup
    this.state.blockConcurrencyWhile(async () => {
      await this.loadRecentFromStorage();
    });
  }

  async loadRecentFromStorage() {
    const rows = this.state.storage.sql.exec(
      `SELECT * FROM messages ORDER BY ts DESC LIMIT ?`,
      MAX_MESSAGES_IN_MEMORY
    ).toArray().reverse();
    for (const row of rows) this.recent.push(row);
  }

  async handleMessage(ws, userId, text) {
    const msg = { userId, text, ts: Date.now() };

    // Write to durable storage first
    this.state.storage.sql.exec(
      `INSERT INTO messages (user_id, text, ts) VALUES (?, ?, ?)`,
      userId, text, msg.ts
    );

    // Update bounded in-memory ring — oldest message drops off automatically
    this.recent.push(msg);

    // Update session activity timestamp
    const session = this.sessions.get(ws);
    if (session) session.lastSeen = Date.now();

    this.broadcast(JSON.stringify(msg));
  }

  evictStaleSessions() {
    const now     = Date.now();
    const staleIds = [];
    for (const [id, session] of this.sessions) {
      if (now - session.lastSeen > SESSION_IDLE_EVICT_MS) {
        staleIds.push(id);
        try { session.ws.close(1001, 'idle timeout'); } catch {}
      }
    }
    for (const id of staleIds) this.sessions.delete(id);
  }

  broadcast(msg) {
    for (const { ws } of this.sessions.values()) {
      try { ws.send(msg); } catch {}
    }
  }
}
```

## Section 3 — DO Alarms for Scheduled Memory Housekeeping

Use **DO Alarms** to run periodic cleanup without relying on request-driven logic:

```javascript
// src/ChatRoomDO.js (continued)
export class ChatRoomDO {
  // ... constructor from Section 2 ...

  async fetch(request) {
    const url = new URL(request.url);

    // Ensure a periodic alarm is always scheduled
    const alarmTime = await this.state.storage.getAlarm();
    if (alarmTime === null) {
      // Schedule cleanup every 5 minutes
      await this.state.storage.setAlarm(Date.now() + 5 * 60 * 1000);
    }

    if (url.pathname === '/ws') {
      return this.handleWebSocketUpgrade(request);
    }

    return new Response('Not found', { status: 404 });
  }

  async alarm() {
    // 1. Evict idle sessions from memory
    this.evictStaleSessions();

    // 2. Prune old messages from SQLite to keep storage compact
    const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000; // 7 days
    this.state.storage.sql.exec(
      `DELETE FROM messages WHERE ts < ?`, cutoff
    );

    // 3. Re-synchronize in-memory ring from storage after pruning
    this.recent = new RingBuffer(MAX_MESSAGES_IN_MEMORY);
    await this.loadRecentFromStorage();

    // 4. Reschedule the alarm
    await this.state.storage.setAlarm(Date.now() + 5 * 60 * 1000);
  }
}
```

Alarms fire even when no WebSocket or HTTP request is active, making them the correct hook for memory and storage housekeeping.

## Section 4 — Lazy Loading and Demand-Paged Storage Reads

Instead of loading all state into memory during the constructor, use **demand-paged reads** that fetch data only when needed and evict it from memory after use:

```javascript
// src/DocumentDO.js
const SECTION_CACHE_MAX = 20;  // max sections held in memory at once

export class DocumentDO {
  constructor(state, env) {
    this.state        = state;
    this.sectionCache = new Map();  // sectionId → { data, lastAccess }
  }

  async getSection(sectionId) {
    // Cache hit
    if (this.sectionCache.has(sectionId)) {
      const entry = this.sectionCache.get(sectionId);
      entry.lastAccess = Date.now();
      return entry.data;
    }

    // Cache miss — load from SQLite
    const row = this.state.storage.sql.exec(
      `SELECT content FROM sections WHERE id = ?`, sectionId
    ).one();

    const data = row ? JSON.parse(row.content) : null;

    // Evict LRU entry if cache is full
    if (this.sectionCache.size >= SECTION_CACHE_MAX) {
      let oldest = null, oldestTime = Infinity;
      for (const [id, entry] of this.sectionCache) {
        if (entry.lastAccess < oldestTime) {
          oldest     = id;
          oldestTime = entry.lastAccess;
        }
      }
      this.sectionCache.delete(oldest);
    }

    this.sectionCache.set(sectionId, { data, lastAccess: Date.now() });
    return data;
  }

  async updateSection(sectionId, newContent) {
    const contentStr = JSON.stringify(newContent);
    this.state.storage.sql.exec(
      `INSERT INTO sections (id, content, updated_at)
       VALUES (?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET content = excluded.content,
                                     updated_at = excluded.updated_at`,
      sectionId, contentStr, Date.now()
    );

    // Update in-memory cache if present
    if (this.sectionCache.has(sectionId)) {
      this.sectionCache.get(sectionId).data = newContent;
    }
  }
}
```

This LRU section cache keeps at most 20 sections in memory regardless of how many sections the document has.  The memory ceiling for this structure is `20 × average_section_size`.

## Anti-patterns

- **Storing large blobs in-memory between requests** — if a DO receives a large payload (image upload, document body), process it immediately and write to R2/storage.  Never accumulate blobs in instance variables.
- **Using `Map` or `Set` with integer keys as sparse arrays** — JavaScript Maps with thousands of integer keys consume more memory than typed arrays.  For numeric data (scores, coordinates), use `Float64Array` or `Int32Array` which are far more memory-compact.
- **Not handling WebSocket close events** — every unhandled closed WebSocket in `this.sessions` is a memory leak.  Always call `this.sessions.delete(id)` in `webSocketClose`.
- **Building entire document history in the constructor** — loading unbounded history from storage into memory during `blockConcurrencyWhile` can cause the DO to exceed the memory limit before it serves a single request.  Load only recent history with a `LIMIT` clause.
- **Recursive in-memory JSON state graphs** — circular references in instance variables prevent garbage collection.  Use flat Maps with explicit ID references, not nested object trees.

## Gotchas

- Cloudflare does **not** currently expose a programmatic memory API inside DOs.  The diagnostic JSON-size estimate in Section 1 is a proxy; actual V8 heap includes overhead per object (typically 2–4× the raw data size for small objects).
- Durable Object **eviction** (due to inactivity) does not persist in-memory state.  On next activation, the DO's constructor runs again from scratch.  Always treat in-memory state as a cache over durable storage — never as the source of truth.
- `state.storage.setAlarm()` requires the alarm to be at least 1 second in the future.  Setting `Date.now() + 0` schedules an immediate alarm, which may fire before the current request completes.
- DO SQLite storage has a **10 GB total size limit** per DO instance and a 4 GB per-row limit (effectively).  Prune old rows proactively; do not assume unlimited storage.
- Memory is not shared between DO instances.  Each `idFromName` creates a separate isolate.  If you need shared state across DO instances, you must use KV (eventual) or a parent DO that coordinates children.

## Verification

1. Write a load test that sends 1,000 messages to a single ChatRoom DO instance over 10 minutes.  Monitor the `/_diag/memory` endpoint every 30 seconds.  After applying the RingBuffer fix, `messagesCount` should plateau at `MAX_MESSAGES_IN_MEMORY`, not grow linearly.
2. Connect 50 WebSocket clients to the DO, then close 40 of them abruptly (kill the client process, do not send a close frame).  After 10 minutes (idle eviction threshold), verify that `sessions.size` drops back to 10, not stays at 50.
3. Deploy with `wrangler tail` and trigger the alarm manually via `wrangler durable-objects alarm trigger`.  Confirm the alarm handler runs without throwing and that the SQLite row count for messages decreases if records older than 7 days exist.

## Related

- `durable-objects-low-latency-stateful.md` — DO fundamentals and storage API
- `durable-objects-websocket-efficiency.md` — WebSocket hibernation for memory efficiency
- `workers-cpu-time-optimization.md` — CPU and memory budget management
- `d1-query-optimization.md` — SQLite query patterns applicable to DO SQLite API
- `garbage-collection-optimization.md` — general JS GC and memory patterns

## Sources

- Durable Objects limits: https://developers.cloudflare.com/durable-objects/platform/limits/
- DO Storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- DO Alarms API: https://developers.cloudflare.com/durable-objects/api/alarms/
- WebSocket Hibernation: https://developers.cloudflare.com/durable-objects/api/websockets/
