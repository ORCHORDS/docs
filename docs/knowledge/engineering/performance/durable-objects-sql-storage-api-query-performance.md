# Durable Objects SQL Storage API — Query Performance Optimization

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Durable Object migrated from key-value `storage.get/put` to the new SQL Storage API
sees unexpectedly high CPU time per request. CRUD operations that should take <1 ms
against a small SQLite database inside the DO are measuring 5–15 ms. Profiling reveals
that DDL statements (`CREATE TABLE IF NOT EXISTS`) are executing on every request
activation, and queries lack indexes on common filter columns.

## Context

The Durable Objects SQL Storage API (`this.ctx.storage.sql`) exposes a synchronous
SQLite interface colocated with the DO's state. Unlike D1, which is a separate
regional service, the SQL database lives *in the same process* as the DO's JavaScript
— no network hop, no serialisation overhead for reads. This makes it extremely fast
for small, hot datasets, but naive schema setup and unindexed queries squander that
advantage. The database persists across hibernation; one-time setup should be guarded
so it runs only when the schema is absent.

## Schema Initialisation — Run Once, Not Per Activation

```typescript
export class GameRoom extends DurableObject {
  private ready = false;

  private ensureSchema(): void {
    if (this.ready) return; // guard against re-runs after hibernation wake

    this.ctx.storage.sql.exec(`
      CREATE TABLE IF NOT EXISTS players (
        id       TEXT PRIMARY KEY,
        name     TEXT NOT NULL,
        score    INTEGER NOT NULL DEFAULT 0,
        joined   INTEGER NOT NULL  -- unix epoch ms
      );
      CREATE INDEX IF NOT EXISTS idx_players_score ON players (score DESC);
      CREATE INDEX IF NOT EXISTS idx_players_joined ON players (joined);
    `);

    this.ready = true;
  }

  async fetch(request: Request): Promise<Response> {
    this.ensureSchema();
    // ... handle request
    return new Response('ok');
  }
}
```

## Parameterised Queries with `sql.exec()`

Avoid string interpolation — use positional parameters to prevent injection and
enable SQLite's statement cache.

```typescript
async addPlayer(id: string, name: string): Promise<void> {
  this.ensureSchema();
  this.ctx.storage.sql.exec(
    'INSERT OR IGNORE INTO players (id, name, joined) VALUES (?, ?, ?)',
    id,
    name,
    Date.now(),
  );
}

async getTopPlayers(limit = 10): Promise<Array<{ id: string; name: string; score: number }>> {
  this.ensureSchema();
  const cursor = this.ctx.storage.sql.exec<{ id: string; name: string; score: number }>(
    'SELECT id, name, score FROM players ORDER BY score DESC LIMIT ?',
    limit,
  );
  return [...cursor]; // cursor is synchronous; spread to array immediately
}
```

## Batch Mutations in a Single Transaction

`sql.exec()` outside an explicit transaction auto-commits each statement. Wrapping
multiple writes in `BEGIN / COMMIT` is ~5–10× faster for bulk operations because WAL
entries are written once.

```typescript
async bulkUpdateScores(
  updates: Array<{ id: string; delta: number }>,
): Promise<void> {
  this.ensureSchema();
  const sql = this.ctx.storage.sql;

  sql.exec('BEGIN');
  try {
    for (const { id, delta } of updates) {
      sql.exec('UPDATE players SET score = score + ? WHERE id = ?', delta, id);
    }
    sql.exec('COMMIT');
  } catch (err) {
    sql.exec('ROLLBACK');
    throw err;
  }
}
```

## Query Plan Inspection with `EXPLAIN QUERY PLAN`

Use EXPLAIN inside a test Worker (or `wrangler dev`) to verify index usage before
shipping to production.

```typescript
// Diagnostic-only: not for production hot path
async explainQuery(query: string, ...params: unknown[]): Promise<unknown[]> {
  const cursor = this.ctx.storage.sql.exec(
    `EXPLAIN QUERY PLAN ${query}`,
    ...params,
  );
  return [...cursor];
  // Look for "USING INDEX" in the 'detail' column.
  // "SCAN TABLE players" without index means a full table scan.
}

// Example: verify top-scores query uses idx_players_score
// explainQuery('SELECT id, score FROM players ORDER BY score DESC LIMIT 10')
// Expected output: USING INDEX idx_players_score
```

## Hybrid KV + SQL: Hot-Path Reads via Cache Layer

For read-heavy patterns (leaderboard polling), cache the result in DO instance memory
to avoid re-running the SQLite query on every request within the same activation
window.

```typescript
export class Leaderboard extends DurableObject {
  private cache: { ts: number; data: unknown[] } | null = null;
  private readonly TTL_MS = 1_000; // 1 s in-memory TTL

  async getLeaderboard(): Promise<unknown[]> {
    const now = Date.now();
    if (this.cache && now - this.cache.ts < this.TTL_MS) {
      return this.cache.data;
    }

    this.ensureSchema();
    const data = [...this.ctx.storage.sql.exec(
      'SELECT id, name, score FROM players ORDER BY score DESC LIMIT 50',
    )];
    this.cache = { ts: now, data };
    return data;
  }
}
```

## Anti-patterns

- **DDL on every `fetch()` call** — `CREATE TABLE IF NOT EXISTS` triggers a full
  schema parse even when the table exists; guard with a boolean flag set after first
  successful init.
- **Spreading a large cursor into an array when only the first row is needed** — use
  `cursor.next().value` for single-row queries; spreading materialises all rows.
- **String-concatenated query parameters** — bypasses SQLite's prepared-statement
  cache and opens injection risk even though the DO is server-side.
- **Storing blobs larger than ~1 MB in SQL columns** — prefer `storage.put()` for
  binary payloads; SQL is optimised for structured rows, not BLOBs.

## Gotchas

- `ctx.storage.sql` is synchronous — it runs on the JS microtask queue but does not
  return a Promise. Do not `await` it; do not mix with async `storage.get()` calls
  inside the same logical transaction.
- The in-process SQLite database is *not* shared across DO stubs pointing to the same
  ID — there is exactly one instance per DO ID. Horizontal read scale requires
  replicating data out (e.g., to D1 or KV) or routing reads to the DO.
- After hibernation, the `ready` flag resets to `false` (class instance is
  re-instantiated). The schema persists in durable storage, but `ensureSchema()` will
  re-run the `CREATE TABLE IF NOT EXISTS` check — cheap, but unavoidable.
- `sql.exec()` raises a synchronous exception on SQL errors; wrap in try/catch,
  especially around `BEGIN/COMMIT` blocks.

## Verification

```typescript
// In wrangler dev: measure query time
const t0 = performance.now();
const rows = [...this.ctx.storage.sql.exec('SELECT COUNT(*) as n FROM players')];
console.log('query_ms', performance.now() - t0, 'rows', rows[0].n);
// Target: <1 ms for indexed queries on tables with <10 k rows
```

```bash
# Confirm DO SQL feature flag is enabled in wrangler.toml
grep -A5 'durable_objects' wrangler.toml
# Requires: compatibility_date >= "2024-04-03"
```

## Related

- `durable-objects-memory-optimization.md` — managing in-process memory
- `durable-objects-read-cache-layer.md` — caching upstream data inside a DO
- `d1-pragma-optimize-query-planner.md` — SQLite planner hints (applies to DO SQL too)
- `durable-objects-rpc-batch-coalescing.md` — reducing per-request DO invocations

## Sources

- Cloudflare Docs: [Durable Objects SQL Storage](https://developers.cloudflare.com/durable-objects/api/storage-api/#sql-storage)
- SQLite EXPLAIN QUERY PLAN: https://www.sqlite.org/eqp.html
- Cloudflare Blog: "Durable Objects: now with SQL" (2024)
