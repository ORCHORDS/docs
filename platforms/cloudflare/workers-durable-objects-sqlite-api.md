# Durable Objects with SQLite Storage API

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need strongly-consistent, low-latency per-entity storage inside a Durable Object — a game session, a collaborative document, a rate limiter — and the classic key-value `this.ctx.storage.get/put` API is either too verbose or too slow for relational queries across multiple keys.

## Context

As of 2024, Durable Objects support an embedded **SQLite storage API** via `this.ctx.storage.sql`. Each DO instance gets its own isolated SQLite database co-located with the DO. The SQLite API is fully synchronous-looking (uses `cursor` objects) and runs in WAL mode by default, giving you read-your-writes consistency and significantly better write throughput than the KV storage API for workloads with many small writes.

---

## Section 1 — Basic Setup and Schema Migration

```toml
# wrangler.toml
name = "durable-objects-sqlite-demo"
main = "src/index.ts"
compatibility_date = "2025-01-01"
compatibility_flags = ["nodejs_compat"]

[[durable_objects.bindings]]
name       = "SESSIONS"
class_name = "SessionDO"

[[migrations]]
tag  = "v1"
new_sqlite_classes = ["SessionDO"]
```

Note: use `new_sqlite_classes` (not `new_classes`) to enable the SQLite backend. Existing DOs using `new_classes` use the key-value backend and cannot be migrated in place.

---

## Section 2 — Durable Object Class with SQL Storage

```typescript
// src/session-do.ts
import type { DurableObjectState, DurableObjectStorage } from '@cloudflare/workers-types';

interface SessionRow {
  id: string;
  user_id: string;
  data: string;  // JSON blob
  created_at: number;
  updated_at: number;
}

interface MessageRow {
  seq: number;
  session_id: string;
  role: string;
  content: string;
  ts: number;
}

export class SessionDO {
  private sql: DurableObjectStorage['sql'];

  constructor(private ctx: DurableObjectState) {
    this.sql = ctx.storage.sql;
    // blockConcurrencyWhile ensures schema is applied before any request is served
    ctx.blockConcurrencyWhile(async () => this.migrate());
  }

  private migrate(): void {
    // DDL runs synchronously; exec() returns a SqlStorageCursor
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS sessions (
        id         TEXT PRIMARY KEY,
        user_id    TEXT NOT NULL,
        data       TEXT NOT NULL DEFAULT '{}',
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
      );

      CREATE TABLE IF NOT EXISTS messages (
        seq        INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        role       TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
        content    TEXT NOT NULL,
        ts         INTEGER NOT NULL
      );

      CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, seq);
    `);
  }

  // Upsert a session
  upsertSession(id: string, userId: string, data: Record<string, unknown>): void {
    const now = Date.now();
    this.sql.exec(
      `INSERT INTO sessions (id, user_id, data, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         data       = excluded.data,
         updated_at = excluded.updated_at`,
      id,
      userId,
      JSON.stringify(data),
      now,
      now
    );
  }

  // Append a message and return the new sequence number
  appendMessage(sessionId: string, role: string, content: string): number {
    const cursor = this.sql.exec(
      `INSERT INTO messages (session_id, role, content, ts)
       VALUES (?, ?, ?, ?)
       RETURNING seq`,
      sessionId,
      role,
      content,
      Date.now()
    );
    const row = cursor.one() as { seq: number };
    return row.seq;
  }

  // Fetch last N messages for a session
  getMessages(sessionId: string, limit = 50): MessageRow[] {
    const cursor = this.sql.exec<MessageRow>(
      `SELECT seq, session_id, role, content, ts
       FROM messages
       WHERE session_id = ?
       ORDER BY seq DESC
       LIMIT ?`,
      sessionId,
      limit
    );
    // toArray() materialises the cursor
    return cursor.toArray().reverse();
  }

  // Token-usage aggregation example
  getSessionStats(sessionId: string): { total: number; byRole: Record<string, number> } {
    const cursor = this.sql.exec<{ role: string; cnt: number }>(
      `SELECT role, COUNT(*) as cnt FROM messages WHERE session_id = ? GROUP BY role`,
      sessionId
    );
    const byRole: Record<string, number> = {};
    let total = 0;
    for (const row of cursor) {
      byRole[row.role] = row.cnt;
      total += row.cnt;
    }
    return { total, byRole };
  }

  async fetch(request: Request): Promise<Response> {
    const { pathname } = new URL(request.url);

    if (request.method === 'POST' && pathname === '/session') {
      const body = await request.json<{ id: string; userId: string; data?: Record<string, unknown> }>();
      this.upsertSession(body.id, body.userId, body.data ?? {});
      return Response.json({ ok: true });
    }

    if (request.method === 'POST' && pathname === '/message') {
      const body = await request.json<{ sessionId: string; role: string; content: string }>();
      const seq = this.appendMessage(body.sessionId, body.role, body.content);
      return Response.json({ seq });
    }

    if (request.method === 'GET' && pathname === '/messages') {
      const url = new URL(request.url);
      const sessionId = url.searchParams.get('sessionId') ?? '';
      const limit = Number(url.searchParams.get('limit') ?? 50);
      const messages = this.getMessages(sessionId, limit);
      return Response.json(messages);
    }

    if (request.method === 'GET' && pathname === '/stats') {
      const sessionId = new URL(request.url).searchParams.get('sessionId') ?? '';
      return Response.json(this.getSessionStats(sessionId));
    }

    return new Response('Not found', { status: 404 });
  }
}
```

---

## Section 3 — Worker Entry Point

```typescript
// src/index.ts
import { SessionDO } from './session-do';
export { SessionDO };

interface Env {
  SESSIONS: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Route by session id from header or query param
    const sessionId = new URL(request.url).searchParams.get('session') ?? 'default';
    const id = env.SESSIONS.idFromName(sessionId);
    const stub = env.SESSIONS.get(id);
    return stub.fetch(request);
  },
};
```

---

## Section 4 — Migration Patterns (KV → SQLite)

You cannot migrate an existing DO class from KV to SQLite in place. The recommended pattern:

1. Create a **new** DO class (`SessionDOV2`) with `new_sqlite_classes`.
2. Deploy the Worker with both classes live.
3. On first request to the new class, lazy-migrate KV data by reading from the old stub via RPC and writing into SQLite.
4. After a migration window, remove the old class migration entry.

```typescript
// One-time lazy migration helper inside SessionDOV2.migrate()
private async lazyMigrateFromKV(oldStub: DurableObjectStub): Promise<void> {
  const alreadyMigrated = this.sql
    .exec(`SELECT 1 FROM kv_migration_done LIMIT 1`)
    .toArray();
  if (alreadyMigrated.length > 0) return;

  // Fetch legacy data via RPC or HTTP from old DO
  const res = await oldStub.fetch('http://do/export');
  const legacy = await res.json<Record<string, unknown>>();

  // Replay into SQLite
  for (const [key, value] of Object.entries(legacy)) {
    this.sql.exec(`INSERT OR IGNORE INTO kv_compat (key, value) VALUES (?, ?)`,
      key, JSON.stringify(value));
  }

  this.sql.exec(`CREATE TABLE IF NOT EXISTS kv_migration_done (done INTEGER)`);
  this.sql.exec(`INSERT INTO kv_migration_done VALUES (1)`);
}
```

---

## Anti-patterns

- **Using `new_classes` instead of `new_sqlite_classes`** — you get the KV backend silently; there is no error. Check the wrangler output for `sqlite` in the migration tags.
- **Running DDL on every request** — use `blockConcurrencyWhile` in the constructor so schema setup happens once before any request is served.
- **Calling `cursor.toArray()` on unbounded queries** — for large tables always add `LIMIT` or iterate the cursor lazily with `for...of`.
- **Storing blobs larger than 2 MB in SQLite columns** — store to R2 and keep only the R2 key in the DB column.

## Gotchas

- `this.sql.exec()` is **synchronous** — it does not return a Promise. Do not `await` it.
- `cursor.one()` throws if zero rows are returned. Use `cursor.toArray()[0]` when the row might not exist.
- SQLite inside a DO has a **1 GB storage limit** per instance. Monitor via `this.ctx.storage.getCurrentBookmark()` (available in newer runtimes).
- WAL mode is always on; you cannot disable it. Reads never block writes — this is intentional.
- The SQLite API is only available for classes declared with `new_sqlite_classes`. Accessing `this.ctx.storage.sql` on a KV-backed DO throws at runtime.

## Verification

```bash
# Run local dev
wrangler dev

# Create a session
curl -X POST 'http://localhost:8787/?session=test-1' \
  -H 'Content-Type: application/json' \
  -d '{"path":"/session","id":"s1","userId":"u1"}'

# Append a message
curl -X POST 'http://localhost:8787/?session=test-1' \
  -H 'Content-Type: application/json' \
  -d '{"path":"/message","sessionId":"s1","role":"user","content":"Hello"}'

# Fetch messages
curl 'http://localhost:8787/?session=test-1&path=/messages&sessionId=s1'
```

## Related

- `workers-analytics-engine-sql-api.md` — aggregating DO-emitted metrics at account scale
- `cloudflare-ai-gateway-prompt-logging-d1.md` — persisting AI logs from DO-based chat sessions

## Sources

- https://developers.cloudflare.com/durable-objects/api/storage-api/#sql-storage-backend
- https://developers.cloudflare.com/durable-objects/best-practices/sqlite/
- https://developers.cloudflare.com/durable-objects/reference/in-memory-state/
