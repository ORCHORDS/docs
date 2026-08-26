# Durable Objects Built-in SQL Storage API

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You need per-entity relational state — per-user game state, per-room chat history, per-session
shopping cart — that must be strongly consistent, low-latency, and isolated from other entities.
D1 is shared and serialises all writes through one primary; a Durable Object with its own SQLite
storage gives each entity a **private, co-located SQLite database** with zero contention from other
entities.

## Context

Cloudflare's Durable Objects platform (2024+) ships a **SQL storage API** (`state.storage.sql`)
that exposes a full SQLite dialect directly inside the DO. Unlike D1 (which is a managed,
remotely-accessed database), DO SQLite storage runs in the same isolate as your object code,
meaning queries are synchronous-from-the-perspective-of-the-DO event loop and sub-millisecond.

Each DO instance gets its own SQLite file. This is ideal for fine-grained, isolated entities.
Cross-entity JOINs are not possible — for reporting across entities, mirror data to D1 via a
change-event pattern.

---

## Environment and Class Setup

```toml
# wrangler.toml
[[durable_objects.bindings]]
name       = "ROOM"
class_name = "ChatRoom"

[[migrations]]
tag = "v1"
new_classes = ["ChatRoom"]
```

```typescript
// src/types.ts
export interface Env {
  ROOM: DurableObjectNamespace;
}
```

---

## Durable Object with SQL Storage

```typescript
// src/do/ChatRoom.ts
import { DurableObject } from "cloudflare:workers";

export class ChatRoom extends DurableObject {
  private sql: SqlStorage;

  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
    this.sql = state.storage.sql;
    this.#migrate();
  }

  #migrate(): void {
    // exec() runs DDL synchronously — safe in constructor
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS messages (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    TEXT    NOT NULL,
        body       TEXT    NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (unixepoch())
      );
      CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);
    `);
  }

  async fetch(request: Request): Promise<Response> {
    const url    = new URL(request.url);
    const action = url.pathname.split("/").pop();

    if (request.method === "POST" && action === "send") {
      return this.#handleSend(request);
    }
    if (request.method === "GET" && action === "history") {
      return this.#handleHistory(url);
    }
    return new Response("Not found", { status: 404 });
  }

  #handleSend(request: Request): Promise<Response> {
    return request.json<{ userId: string; body: string }>().then(({ userId, body }) => {
      // cursor() returns a SqlStorageCursor (iterable)
      const rows = [
        ...this.sql
          .exec("INSERT INTO messages (user_id, body) VALUES (?, ?) RETURNING id, created_at", userId, body)
      ];
      return Response.json(rows[0]);
    });
  }

  #handleHistory(url: URL): Response {
    const limit  = Number(url.searchParams.get("limit")  ?? 50);
    const before = Number(url.searchParams.get("before") ?? Date.now() / 1000);

    const rows = [
      ...this.sql.exec(
        `SELECT id, user_id, body, created_at
           FROM messages
          WHERE created_at < ?
          ORDER BY created_at DESC
          LIMIT ?`,
        before,
        limit
      ),
    ];
    return Response.json(rows.reverse()); // chronological order
  }
}
```

---

## Worker Entrypoint: Routing to a Room

```typescript
// src/index.ts
export { ChatRoom } from "./do/ChatRoom";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url    = new URL(request.url);
    const roomId = url.searchParams.get("roomId");
    if (!roomId) return new Response("Missing roomId", { status: 400 });

    const id   = env.ROOM.idFromName(roomId);
    const stub = env.ROOM.get(id);

    // Forward the full request to the DO
    return stub.fetch(request);
  },
};
```

---

## Aggregated Reporting via D1 Mirror

DO SQLite is isolated; for cross-room analytics, emit events to D1:

```typescript
// inside ChatRoom, after the INSERT:
async #mirrorToD1(env: Env, payload: { roomId: string; userId: string; createdAt: number }) {
  // Use a service binding or fetch to a Worker that writes to D1
  await fetch("https://internal.example project.example.com/analytics/chat-event", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  });
}
```

---

## Counting and Storage Introspection

```typescript
// How much SQLite storage is this DO using?
async getStorageStats(): Promise<Response> {
  const [stats] = [...this.sql.exec(
    "SELECT page_count * page_size AS used_bytes FROM pragma_page_count(), pragma_page_size()"
  )];
  const databaseSize = this.sql.databaseSize; // built-in property, in bytes
  return Response.json({ databaseSize, fromPragma: stats.used_bytes });
}
```

---

## Anti-patterns

- **Storing global lookup tables in DO SQLite**: DO SQLite is per-instance; a lookup that spans
  many entities belongs in D1 or KV, not replicated inside every DO.
- **Issuing cross-DO SQL JOINs**: not possible. Use D1 or an analytical store for cross-entity
  aggregation.
- **Running DDL on every `fetch()` call**: migrations are idempotent but wasteful; run them once in
  the constructor (or in a `state.blockConcurrencyWhile` block).
- **Forgetting `state.blockConcurrencyWhile`**: if your constructor performs async work that must
  complete before any requests are handled, wrap it; otherwise requests may race with initialisation.

---

## Gotchas

- **DO SQLite is NOT D1**: it is available only inside Durable Object classes via `state.storage.sql`.
  Worker scripts (without a DO) cannot access this API.
- `sql.exec()` is **synchronous** in the sense that it returns a cursor; the cursor is iterable and
  results materialise lazily. Spread `[...cursor]` to collect all rows before the function returns.
- DO SQLite has a **10 GB per-instance storage limit**. For unbounded data (chat rooms with years of
  history) implement TTL-based pruning or partition data by time into separate DO instances.
- **Hibernation and SQLite state**: when a DO hibernates, its SQLite data persists on disk. On
  wake, the constructor runs again — always call `#migrate()` in the constructor, not in `alarm()`.
- `sql.exec()` does not support named parameters (`:name`). Use positional `?` placeholders only.

---

## Verification

```bash
# Create a room and send a message
curl -s -X POST "https://example project.example.com/?roomId=room-1" \
  -H "Content-Type: application/json" \
  -d '{"userId":"u-1","body":"hello world"}'
# {"id":1,"created_at":1753228800}

# Retrieve history
curl -s "https://example project.example.com/?roomId=room-1&action=history"
# [{"id":1,"user_id":"u-1","body":"hello world","created_at":1753228800}]

# Verify storage size
curl -s "https://example project.example.com/?roomId=room-1&action=stats"
# {"databaseSize":32768,"fromPragma":32768}
```

---

## Related

- `d1-durable-objects-serialized-writes-workers.md`
- `d1-durable-object-connection-multiplexing-workers.md`
- `d1-event-sourcing-append-only-log.md`
- `d1-crdt-offline-sync.md`
- `sqlite-journal-modes.md`

## Sources

- Cloudflare Durable Objects SQL storage: https://developers.cloudflare.com/durable-objects/api/storage-api/#sql-storage
- DO storage limits: https://developers.cloudflare.com/durable-objects/platform/limits/
- DO hibernation: https://developers.cloudflare.com/durable-objects/reference/in-memory-state/
