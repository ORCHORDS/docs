# Batch INSERT Performance Tuning in D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to ingest large volumes of rows into a Cloudflare D1 database — e.g. syncing a third-party dataset, bulk-importing a CSV, or writing thousands of analytics events in a single Worker invocation. Naïve single-row INSERTs are 10–50× slower than batched approaches and will hit D1's per-request CPU limits.

## Context

D1 is Cloudflare's serverless SQLite-compatible database. It runs on the edge and is accessed via the `env.DB` binding inside a Worker. Three distinct write strategies exist:

1. **Single-row INSERT** — one `prepare().bind().run()` per row.
2. **Multi-row VALUES INSERT** — one SQL statement with many `(?, ?)` value groups.
3. **`env.DB.batch()`** — a single round-trip that executes multiple prepared statements atomically.

Each strategy has different throughput characteristics, payload limits, and error semantics. `meta.duration` (returned in every D1 result object) gives you the server-side SQL execution time in milliseconds, which is the right metric to compare — not wall-clock time, which includes network and serialisation overhead.

## Implementation: Three Strategies Compared

```typescript
type Row = { id: number; name: string; score: number };

// ─── Utility ────────────────────────────────────────────────────────────────

/** Split an array into chunks of at most `size` elements. */
function chunkArray<T>(arr: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    chunks.push(arr.slice(i, i + size));
  }
  return chunks;
}

// ─── Strategy 1: Single-row INSERT (avoid for bulk work) ─────────────────────

async function insertSingleRow(db: D1Database, rows: Row[]): Promise<void> {
  const stmt = db.prepare(
    'INSERT OR IGNORE INTO scores (id, name, score) VALUES (?, ?, ?)'
  );
  for (const row of rows) {
    const result = await stmt.bind(row.id, row.name, row.score).run();
    console.log('duration_ms:', result.meta.duration);
  }
}

// ─── Strategy 2: Multi-row VALUES INSERT ─────────────────────────────────────
//
// D1 payload limit: ~1 MB per request. A safe upper bound is ~200 rows
// per statement for typical row sizes (< 1 KB each).

async function insertMultiRow(
  db: D1Database,
  rows: Row[],
  chunkSize = 200
): Promise<void> {
  for (const chunk of chunkArray(rows, chunkSize)) {
    const placeholders = chunk.map(() => '(?, ?, ?)').join(', ');
    const values = chunk.flatMap((r) => [r.id, r.name, r.score]);
    const result = await db
      .prepare(`INSERT OR IGNORE INTO scores (id, name, score) VALUES ${placeholders}`)
      .bind(...values)
      .run();
    console.log(`chunk=${chunk.length} duration_ms=${result.meta.duration}`);
  }
}

// ─── Strategy 3: env.DB.batch() — recommended for mixed workloads ─────────────
//
// batch() sends all statements in one HTTP round-trip and executes them
// inside a single implicit transaction. Max ~100 statements per batch
// is a practical limit before the request payload approaches 1 MB.

async function insertBatch(
  db: D1Database,
  rows: Row[],
  chunkSize = 100
): Promise<void> {
  const stmt = db.prepare(
    'INSERT OR REPLACE INTO scores (id, name, score) VALUES (?, ?, ?)'
  );
  for (const chunk of chunkArray(rows, chunkSize)) {
    const statements = chunk.map((r) => stmt.bind(r.id, r.name, r.score));
    const results = await db.batch(statements);
    const totalDuration = results.reduce((s, r) => s + r.meta.duration, 0);
    console.log(`batch=${chunk.length} total_duration_ms=${totalDuration}`);
  }
}

// ─── Benchmark harness ───────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const rows: Row[] = Array.from({ length: 1000 }, (_, i) => ({
      id: i + 1,
      name: `item_${i}`,
      score: Math.random() * 100,
    }));

    const t0 = Date.now();
    await insertBatch(env.DB, rows);
    const elapsed = Date.now() - t0;

    return Response.json({ elapsed_ms: elapsed, rows: rows.length });
  },
};
```

## Choosing Between `INSERT OR IGNORE` and `INSERT OR REPLACE`

| Strategy | Behaviour on conflict | Use when |
|---|---|---|
| `INSERT OR IGNORE` | Skips the conflicting row silently | Idempotent bulk load; existing data must not change |
| `INSERT OR REPLACE` | Deletes the old row and inserts a new one | Upsert semantics; you want the latest value to win |
| `INSERT OR ROLLBACK` (default) | Aborts the entire statement on conflict | Strict uniqueness enforcement |

For bulk imports where the source may contain duplicates, `INSERT OR IGNORE` is the safest choice. `INSERT OR REPLACE` is useful for sync pipelines where the latest record should always win, but note that it increments the row's `rowid` (which can matter for triggers or replication).

## Measuring with `meta.duration`

Every D1 result exposes `meta.duration` — the time in milliseconds the query spent executing inside the SQLite engine, excluding network transit. This is the correct metric for comparing strategies:

```typescript
const result = await env.DB.prepare('INSERT INTO ...').bind(...).run();
console.log(JSON.stringify(result.meta));
// { duration: 1.24, rows_read: 0, rows_written: 50, last_row_id: 50, changes: 50 }
```

Typical observations:
- Single-row INSERT: ~2–5 ms per row → 2–5 s for 1 000 rows.
- Multi-row VALUES: ~5–15 ms per 200-row chunk → 25–75 ms for 1 000 rows.
- `batch()` 100-statement: ~10–20 ms per batch → 20–40 ms for 1 000 rows.

## `chunkArray` and the 1 MB Payload Limit

D1 enforces a ~1 MB limit per HTTP request body. A safe heuristic: keep each chunk under 200 rows for multi-row VALUES (depends on row size) and under 100 statements for `batch()`. Exceeding these limits returns a `413 Payload Too Large` error from the D1 API.

The `chunkArray` helper above is intentionally generic — reuse it across all three strategies by adjusting `chunkSize` to match your row byte size.

## Anti-patterns

- **Looping `await stmt.run()` without batching** for more than ~10 rows — each call is a separate round-trip; latency compounds.
- **Unbounded `batch()` calls** with thousands of statements — the request body exceeds 1 MB and fails entirely.
- **Using `INSERT OR REPLACE` naively** when you only want to ignore duplicates — it silently deletes and re-inserts, resetting `created_at` timestamps and incrementing `rowid`.
- **Not wrapping `batch()` in a try/catch** — a single statement error inside a batch causes the entire batch to roll back in some D1 versions.

## Gotchas

- D1 is not Postgres: `ON CONFLICT DO UPDATE` (standard upsert syntax) is available in SQLite ≥ 3.24.0 and D1 supports it, but the binding spread (`...values`) for large tuples can hit V8 argument count limits — use `chunkArray` to stay safe.
- `meta.duration` measures server-side time only. Total wall-clock latency includes the Workers-to-D1 round-trip (~1–5 ms in the same region).
- D1 has a **per-Worker CPU limit**: bulk inserts inside a Worker with a 30 s wall-clock limit should target completion within ~10 s to leave headroom for other processing.

## Verification

```bash
# Create the target table locally
npx wrangler d1 execute MY_DB --local --command \
  "CREATE TABLE IF NOT EXISTS scores (id INTEGER PRIMARY KEY, name TEXT, score REAL)"

# Run the Worker locally and observe batch timing
npx wrangler dev --local
curl http://localhost:8787/
# Expected: {"elapsed_ms": <N>, "rows": 1000}

# Verify row count
npx wrangler d1 execute MY_DB --local --command "SELECT COUNT(*) FROM scores"
```

## Related

- `workers-cache-api-advanced-custom-keys.md`
- `workers-ai-inference-result-caching-kv.md`
- [D1 Workers Binding API — Cloudflare Docs](https://developers.cloudflare.com/d1/worker-api/)

## Sources

- Cloudflare D1 documentation — Worker Binding API (2025)
- SQLite `INSERT OR IGNORE` / `INSERT OR REPLACE` documentation
- Cloudflare D1 limits and known issues (2025)
