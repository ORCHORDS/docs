# D1 Batch Operations and Write-Optimised Query Patterns

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A Cloudflare Workers application using D1 experiences slow bulk writes, N+1 query
patterns from ORM-style code, contention on hot rows during concurrent updates, or
excessive round-trips that inflate response latency. D1 is SQLite under the hood with
an HTTP transport layer between the Worker and the D1 service — each `.run()` or
`.first()` call is a separate network hop within Cloudflare's network (~1–5 ms). At
small scale this is invisible; at scale it compounds into seconds of latency per request.
The D1 batch API, `prepare`/`bind` patterns, `INSERT OR REPLACE` idioms, and write
coalescing with Durable Objects eliminate these problems at the architecture layer.

Concrete triggers:
- Importing 1000 chord definitions at startup — one INSERT per chord is 1000 round-trips
- Logging user events on every API call — causes hot-write contention on the events table
- Fetching a chord and its tags in separate queries (N+1)
- Bulk-updating subscription statuses nightly from a billing webhook

---

## Context

D1 characteristics that shape optimisation strategy:

| Property | Value | Implication |
|----------|-------|-------------|
| Engine | SQLite (WAL mode) | Single-writer at a time; reads scale independently |
| Transport | HTTP/2 RPC | Each statement = 1 network round-trip (~1–5 ms) |
| Batch API | `db.batch([...])` | Multiple statements in one round-trip |
| Max batch size | 100 statements | Split larger payloads into chunks of 100 |
| Row limit per query | 1000 (default) | Use `LIMIT`/`OFFSET` or cursor pagination |
| D1 regions | Multiple (auto-placed) | Reads from nearest replica; writes to primary |
| Max DB size | 10 GB (Workers paid) | Monitor with D1 metrics |

---

## Pattern 1: Batch API for Bulk Writes

The `db.batch()` call executes an array of prepared statements in a single round-trip,
wrapped in an implicit transaction. All succeed or all fail atomically.

### Without batch (N round-trips)

```typescript
// BAD — N separate round-trips for N chords
for (const chord of chords) {
  await env.DB
    .prepare('INSERT INTO chords (id, name, voicing) VALUES (?, ?, ?)')
    .bind(chord.id, chord.name, chord.voicing)
    .run();
}
// 100 chords → ~100 round-trips → ~500 ms at 5 ms/trip
```

### With batch (1 round-trip)

```typescript
// GOOD — all statements in a single round-trip
const BATCH_SIZE = 100; // D1 max batch size

async function bulkInsertChords(
  chords: Array<{ id: string; name: string; voicing: string }>,
  db: D1Database
): Promise<void> {
  // Chunk into batches of 100
  for (let i = 0; i < chords.length; i += BATCH_SIZE) {
    const chunk = chords.slice(i, i + BATCH_SIZE);
    const statements = chunk.map(chord =>
      db.prepare('INSERT OR IGNORE INTO chords (id, name, voicing) VALUES (?, ?, ?)')
        .bind(chord.id, chord.name, chord.voicing)
    );
    await db.batch(statements);
  }
}
// 100 chords → 1 round-trip → ~5 ms
// 1000 chords → 10 round-trips → ~50 ms
```

### Batch with mixed statement types

```typescript
// Atomic upsert: insert chord + update user stats in one transaction
const results = await env.DB.batch([
  env.DB.prepare('INSERT OR REPLACE INTO chords (id, name, voicing) VALUES (?, ?, ?)')
    .bind(chord.id, chord.name, chord.voicing),
  env.DB.prepare('UPDATE users SET chord_count = chord_count + 1 WHERE id = ?')
    .bind(userId),
  env.DB.prepare('INSERT INTO chord_events (chord_id, user_id, action) VALUES (?, ?, ?)')
    .bind(chord.id, userId, 'created'),
]);

// results[0].success, results[1].success, results[2].success
```

---

## Pattern 2: Eliminating N+1 Queries

### N+1 (bad)

```typescript
// Fetches each chord's tags in a separate query — N+1 round-trips
const chords = await env.DB
  .prepare('SELECT * FROM chords WHERE user_id = ? LIMIT 20')
  .bind(userId)
  .all<Chord>();

for (const chord of chords.results) {
  const tags = await env.DB
    .prepare('SELECT tag FROM chord_tags WHERE chord_id = ?')
    .bind(chord.id)
    .all<{ tag: string }>();
  chord.tags = tags.results.map(r => r.tag);
}
// 20 chords → 1 + 20 = 21 round-trips
```

### JOIN with JSON aggregation (1 round-trip)

```typescript
// SQLite's json_group_array / json_each for aggregation
const rows = await env.DB
  .prepare(`
    SELECT
      c.id, c.name, c.voicing, c.created_at,
      json_group_array(ct.tag) FILTER (WHERE ct.tag IS NOT NULL) AS tags_json
    FROM chords c
    LEFT JOIN chord_tags ct ON ct.chord_id = c.id
    WHERE c.user_id = ?
    GROUP BY c.id
    ORDER BY c.created_at DESC
    LIMIT 20
  `)
  .bind(userId)
  .all<{ id: string; name: string; voicing: string; created_at: string; tags_json: string }>();

const chords = rows.results.map(row => ({
  ...row,
  tags: JSON.parse(row.tags_json) as string[],
}));
// 20 chords → 1 round-trip
```

### Batched multi-entity fetch (alternative to JOIN)

```typescript
// When JOIN is complex, batch individual SELECTs
const chordIds = ['id1', 'id2', 'id3'];
const placeholders = chordIds.map(() => '?').join(', ');

const [chordResults, tagResults] = await env.DB.batch([
  env.DB.prepare(`SELECT * FROM chords WHERE id IN (${placeholders})`)
    .bind(...chordIds),
  env.DB.prepare(`SELECT chord_id, tag FROM chord_tags WHERE chord_id IN (${placeholders})`)
    .bind(...chordIds),
]);

// Group tags by chord_id in JS (O(n) — no extra round-trip)
const tagMap = new Map<string, string[]>();
for (const row of (tagResults as D1Result<{ chord_id: string; tag: string }>).results) {
  const tags = tagMap.get(row.chord_id) ?? [];
  tags.push(row.tag);
  tagMap.set(row.chord_id, tags);
}
```

---

## Pattern 3: Write Coalescing with Durable Objects

For high-frequency writes (event logging, metrics, counters), individual INSERTs per
request create write amplification and potential contention. A Durable Object acts as a
write buffer, accumulating writes in memory and flushing to D1 in batches.

```typescript
// src/do/event-buffer.ts
import { DurableObject } from 'cloudflare:workers';

interface UserEvent {
  userId: string;
  action: string;
  metadata: unknown;
  timestamp: number;
}

interface Env {
  DB: D1Database;
  EVENT_BUFFER: DurableObjectNamespace;
}

export class EventBuffer extends DurableObject {
  private buffer: UserEvent[] = [];
  private readonly FLUSH_INTERVAL_MS = 2000; // Flush every 2 seconds
  private readonly FLUSH_BATCH_SIZE = 50;   // Or when buffer hits 50 events

  async fetch(request: Request): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method not allowed', { status: 405 });

    const event = await request.json<UserEvent>();
    this.buffer.push(event);

    if (this.buffer.length >= this.FLUSH_BATCH_SIZE) {
      await this.flush();
    } else {
      // Arm alarm to flush soon if not already armed
      const existing = await this.ctx.storage.getAlarm();
      if (!existing) {
        await this.ctx.storage.setAlarm(Date.now() + this.FLUSH_INTERVAL_MS);
      }
    }

    return Response.json({ ok: true, buffered: this.buffer.length });
  }

  async alarm(): Promise<void> {
    await this.flush();
  }

  private async flush(): Promise<void> {
    if (this.buffer.length === 0) return;

    const toFlush = this.buffer.splice(0, this.FLUSH_BATCH_SIZE);
    const env = this.env as Env;

    const statements = toFlush.map(event =>
      env.DB.prepare(
        'INSERT INTO user_events (user_id, action, metadata, created_at) VALUES (?, ?, ?, ?)'
      ).bind(event.userId, event.action, JSON.stringify(event.metadata), event.timestamp)
    );

    try {
      await env.DB.batch(statements);
    } catch (err) {
      // Put events back in buffer on failure
      this.buffer.unshift(...toFlush);
      throw err;
    }
  }
}
```

```typescript
// Caller Worker — fire and forget via waitUntil
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const response = await handleRequest(request, env);

    // Coalesce event write — do not block the response
    ctx.waitUntil(
      (async () => {
        const doId = env.EVENT_BUFFER.idFromName('events-global');
        const stub = env.EVENT_BUFFER.get(doId);
        await stub.fetch('https://do/', {
          method: 'POST',
          body: JSON.stringify({
            userId: getUserId(request),
            action: 'api_call',
            metadata: { path: new URL(request.url).pathname },
            timestamp: Date.now(),
          }),
        });
      })()
    );

    return response;
  },
};
```

---

## Pattern 4: Upsert Idioms

D1 (SQLite) supports several upsert patterns with different conflict semantics:

```sql
-- INSERT OR IGNORE: silently skip duplicates (no update)
INSERT OR IGNORE INTO chords (id, name, voicing)
VALUES (?, ?, ?);

-- INSERT OR REPLACE: delete + re-insert (resets created_at, loses unspecified columns)
INSERT OR REPLACE INTO chords (id, name, voicing, created_at)
VALUES (?, ?, ?, COALESCE((SELECT created_at FROM chords WHERE id = ?), datetime('now')));

-- INSERT ... ON CONFLICT DO UPDATE (preferred — partial update, preserves other columns)
INSERT INTO chords (id, name, voicing)
VALUES (?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
  name   = excluded.name,
  voicing = excluded.voicing,
  updated_at = datetime('now');
```

```typescript
// Bulk upsert with ON CONFLICT
async function upsertChords(
  chords: Array<{ id: string; name: string; voicing: string }>,
  db: D1Database
): Promise<void> {
  const BATCH_SIZE = 100;
  for (let i = 0; i < chords.length; i += BATCH_SIZE) {
    const chunk = chords.slice(i, i + BATCH_SIZE);
    await db.batch(
      chunk.map(c =>
        db.prepare(`
          INSERT INTO chords (id, name, voicing)
          VALUES (?, ?, ?)
          ON CONFLICT(id) DO UPDATE SET
            name    = excluded.name,
            voicing = excluded.voicing,
            updated_at = datetime('now')
        `).bind(c.id, c.name, c.voicing)
      )
    );
  }
}
```

---

## Pattern 5: Cursor-Based Pagination

D1 enforces a 1000-row limit per query. For large datasets, use cursor pagination
rather than `OFFSET` (which performs a full scan up to the offset):

```typescript
// Cursor-based pagination — O(log n) with index on created_at
async function paginateChords(
  db: D1Database,
  userId: string,
  cursor?: string, // ISO timestamp of last item in previous page
  limit = 20
): Promise<{ items: Chord[]; nextCursor: string | null }> {
  const rows = await db
    .prepare(cursor
      ? 'SELECT * FROM chords WHERE user_id = ? AND created_at < ? ORDER BY created_at DESC LIMIT ?'
      : 'SELECT * FROM chords WHERE user_id = ? ORDER BY created_at DESC LIMIT ?'
    )
    .bind(...(cursor ? [userId, cursor, limit + 1] : [userId, limit + 1]))
    .all<Chord>();

  const items = rows.results.slice(0, limit);
  const nextCursor = rows.results.length > limit
    ? items[items.length - 1].created_at
    : null;

  return { items, nextCursor };
}
```

---

## D1 Schema Optimisations

```sql
-- Index covering common query patterns
CREATE TABLE chords (
  id         TEXT PRIMARY KEY,
  user_id    TEXT NOT NULL,
  name       TEXT NOT NULL,
  voicing    TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Composite index for the most common query: user's recent chords
CREATE INDEX idx_chords_user_recent ON chords (user_id, created_at DESC);

-- Partial index for un-archived chords only
CREATE INDEX idx_chords_active ON chords (user_id)
  WHERE archived_at IS NULL;

-- Events table: append-only, partitioned by date for efficient pruning
CREATE TABLE user_events (
  id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id    TEXT NOT NULL,
  action     TEXT NOT NULL,
  metadata   TEXT,  -- JSON
  created_at INTEGER NOT NULL  -- Unix ms for fast range queries
);

CREATE INDEX idx_events_user_time ON user_events (user_id, created_at DESC);

-- Prune events older than 90 days (run via Cron Worker)
-- DELETE FROM user_events WHERE created_at < unixepoch('now', '-90 days') * 1000;
```

---

## Mobile API Consumer Considerations (example project React Native)

- **Pagination**: All list endpoints must support `cursor`/`limit` query params. Return
  `nextCursor: null` when the last page is reached. The React Native app uses
  `FlatList` with `onEndReached` for infinite scroll — cursors are preferable to pages.
- **Optimistic updates**: When a user saves a chord, update local state immediately
  before the API response. The batch write may complete in <5 ms but network latency
  from the device to the edge adds 50–200 ms.
- **Offline queue**: If the device is offline, queue writes locally (SQLite via MMKV)
  and flush when connectivity returns. The D1 batch API on the server can absorb a
  burst of queued writes when the device reconnects.
- **Rate of event writes**: Mobile apps can generate many events per session (scroll,
  tap, play). Use the DO-based write coalescing pattern to avoid per-event D1 round-trips.

---

## Anti-patterns

- **Executing statements inside a `for` loop with `await`**: The most common D1
  performance anti-pattern. Always batch or use JOINs.
- **Using `SELECT *` with `json_group_array` on large tables**: The aggregation
  happens in SQLite before the row limit. Add `WHERE` filters to bound the result set.
- **Unbounded `IN` clauses**: `WHERE id IN (?, ?, ..., ?)` with 500+ values degrades
  performance. Use a temp table or chunk into batches of 100.
- **Using `OFFSET` pagination**: `SELECT ... LIMIT 20 OFFSET 500` must scan 520 rows
  to return 20. Cursor pagination is O(log n) with an index.
- **Competing writes to the same row from multiple Workers**: D1's WAL mode serialises
  writes. High-concurrency updates to a single counter row (e.g., view count) cause
  lock contention. Use a DO or a separate counter table with periodic rollup.
- **Not using `INSERT OR IGNORE` for idempotent ingestion**: Without it, a duplicate
  key error aborts the entire batch.

---

## Gotchas

- `db.batch()` is atomic: if one statement fails, **all** statements in the batch are
  rolled back. Check `results[i].success` for conditional handling.
- D1's maximum batch size is 100 statements. Batching more than 100 throws a runtime
  error. Always chunk at 100.
- `db.prepare(...).bind(...)` does not execute the query — it returns a `D1PreparedStatement`.
  Call `.run()`, `.first()`, or `.all()` to execute, or pass the prepared statement to
  `db.batch()`.
- D1 prepared statements bind positional parameters with `?` (SQLite style), not `$1`
  (Postgres style). Mixing them causes a runtime error.
- `json_group_array` returns `'[]'` (the string) when there are no matching rows with
  `LEFT JOIN` — always `JSON.parse` and handle the empty array case.
- D1 `INTEGER` columns store 64-bit signed integers. JavaScript's `Number` can represent
  integers up to 2^53 safely. For IDs larger than that, use `TEXT`.

---

## Verification

```bash
# Check slow queries with D1 analytics (Workers dashboard)
# Or run EXPLAIN QUERY PLAN locally

wrangler d1 execute DB --command \
  "EXPLAIN QUERY PLAN SELECT * FROM chords WHERE user_id = 'x' ORDER BY created_at DESC LIMIT 20;"
# Look for: "SEARCH chords USING INDEX idx_chords_user_recent"
# Avoid:    "SCAN chords" (full table scan)

# Benchmark batch vs. sequential writes
wrangler dev
# Run synthetic load test
npx autocannon -d 10 -c 20 -m POST http://localhost:8787/v1/chords/bulk \
  -H "Content-Type: application/json" \
  -b '{"chords": [...]}'
```

---

## Related

- `competing-consumers-durable-objects.md` — DO write buffer for event coalescing
- `cqrs-cloudflare-workers-d1.md` — separating reads and writes in D1
- `read-through-cache.md` — caching D1 query results in KV
- `hyperdrive-postgres-connection-pooling.md` — when D1 is insufficient
- `zero-downtime-schema-migrations.md` — safe D1 schema changes
- `hot-partition-mitigation.md` — handling hot rows in D1

---

## Sources

- Cloudflare D1 documentation (developers.cloudflare.com/d1)
- D1 batch API reference (developers.cloudflare.com/d1/worker-api/d1-database/#batch)
- SQLite query optimiser documentation (sqlite.org/optoverview.html)
- D1 limits and pricing (developers.cloudflare.com/d1/platform/limits)
