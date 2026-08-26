# D1 Import Timing Out on 50k-Row CSV via wrangler d1 execute

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A one-time migration of 50,000 chord-chart records from a legacy Postgres database to Cloudflare D1 failed repeatedly with `Error: Request timeout` after approximately 10 seconds. The exported SQL file was 28 MB and contained 50,000 `INSERT` statements. Running `wrangler d1 execute orchords-db --file migration.sql` would begin execution but never complete, leaving the table in a partially-populated state with no clear row count in the error output.

---

## Context

D1 is Cloudflare's serverless SQLite product. At the time of the incident, the `wrangler d1 execute --file` command sent the entire SQL file to the D1 import HTTP endpoint in a single request. The import endpoint enforces a 10-second HTTP timeout server-side, which is insufficient for executing tens of thousands of `INSERT` statements sequentially. The D1 HTTP API and wrangler CLI do not (yet) automatically chunk large SQL files. The team discovered this limitation mid-migration during a planned maintenance window, blocking the launch by several hours.

---

## What Went Wrong

```bash
# Broken: sending a 28 MB SQL file in a single wrangler command
# This will timeout at ~10 seconds for files > a few thousand rows
wrangler d1 execute orchords-db --file migration.sql --remote

# The generated migration.sql looked like:
# INSERT INTO chord_charts (id, title, artist, bpm, key, content) VALUES (...);
# INSERT INTO chord_charts (id, title, artist, bpm, key, content) VALUES (...);
# ... x 50,000 rows — single transaction, times out before committing
```

```typescript
// Also broken: sending all rows in one Worker request via D1 binding
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const rows: ChordChart[] = await request.json();

    // BAD: D1 batch() is limited to 1000 statements and still subject to
    // the Worker 30s CPU time limit for very large batches
    const stmts = rows.map(row =>
      env.DB.prepare(
        'INSERT INTO chord_charts (id, title, artist, bpm, key, content) VALUES (?, ?, ?, ?, ?, ?)'
      ).bind(row.id, row.title, row.artist, row.bpm, row.key, row.content)
    );

    // Throws if stmts.length > 1000 or if total execution exceeds CPU limit
    await env.DB.batch(stmts);
    return Response.json({ inserted: rows.length });
  },
};
```

## Root Cause

The `wrangler d1 execute --file` command uploads the SQL file to the D1 REST import endpoint (`POST /client/v4/accounts/{id}/d1/database/{db}/import`) as a single HTTP request. This endpoint has a hard server-side 10-second timeout. For a 50k-row INSERT file, sequential execution in SQLite far exceeds 10 seconds even with WAL mode. Additionally, D1's `batch()` API via Worker bindings caps at 1000 statements per call. There is no built-in chunking, retry, or progress mechanism in wrangler for large files.

## The Fix

```bash
#!/usr/bin/env bash
# scripts/d1-chunked-import.sh
# Splits a large SQL INSERT file into 1000-row chunks and imports each chunk sequentially.

set -euo pipefail

SQL_FILE="${1:?Usage: $0 <sql_file> <database_name>}"
DB_NAME="${2:?Usage: $0 <sql_file> <database_name>}"
CHUNK_SIZE=1000
SCRATCH_DIR=$(mktemp -d)

echo "Splitting ${SQL_FILE} into chunks of ${CHUNK_SIZE} rows..."

# Extract header (CREATE TABLE, pragmas, BEGIN TRANSACTION) and footer (COMMIT)
HEADER=$(grep -v '^INSERT' "$SQL_FILE" | head -20)
FOOTER="COMMIT;"

# Split only INSERT lines into chunks
grep '^INSERT' "$SQL_FILE" | split -l "$CHUNK_SIZE" - "${SCRATCH_DIR}/chunk_"

CHUNK_NUM=0
for chunk_file in "${SCRATCH_DIR}"/chunk_*; do
  CHUNK_NUM=$((CHUNK_NUM + 1))
  CHUNK_SQL="${SCRATCH_DIR}/import_chunk_${CHUNK_NUM}.sql"

  # Wrap each chunk in its own transaction for atomicity
  {
    echo "BEGIN TRANSACTION;"
    cat "$chunk_file"
    echo "COMMIT;"
  } > "$CHUNK_SQL"

  echo "Importing chunk ${CHUNK_NUM} (rows $((($CHUNK_NUM-1)*$CHUNK_SIZE+1))-$(($CHUNK_NUM*$CHUNK_SIZE)))..."
  wrangler d1 execute "$DB_NAME" --file "$CHUNK_SQL" --remote
  echo "Chunk ${CHUNK_NUM} done."

  # Small delay to avoid hammering the D1 API
  sleep 0.5
done

echo "Import complete. Total chunks: ${CHUNK_NUM}"
rm -rf "$SCRATCH_DIR"
```

```typescript
// Alternative fix: Worker-based chunked importer using D1 batch() in groups of 1000
// POST /admin/import with JSON body { rows: ChordChart[] }
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { rows }: { rows: ChordChart[] } = await request.json();
    const BATCH_SIZE = 1000;
    let inserted = 0;

    for (let i = 0; i < rows.length; i += BATCH_SIZE) {
      const batch = rows.slice(i, i + BATCH_SIZE);
      const stmts = batch.map(row =>
        env.DB.prepare(
          `INSERT INTO chord_charts (id, title, artist, bpm, key, content)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO NOTHING`
        ).bind(row.id, row.title, row.artist, row.bpm, row.key, row.content)
      );
      await env.DB.batch(stmts);
      inserted += batch.length;
    }

    return Response.json({ inserted });
  },
};

// Caller script (Node.js) sends chunks of 1000 rows at a time:
// import { readFileSync } from 'fs';
// const rows: ChordChart[] = JSON.parse(readFileSync('export.json', 'utf8'));
// const CHUNK = 1000;
// for (let i = 0; i < rows.length; i += CHUNK) {
//   await fetch('https://my-worker.example.workers.dev/admin/import', {
//     method: 'POST',
//     headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${TOKEN}` },
//     body: JSON.stringify({ rows: rows.slice(i, i + CHUNK) }),
//   });
// }
```

```bash
# Best alternative for very large datasets: Hyperdrive-backed Postgres COPY
# If you have a Postgres source, use COPY for bulk insert before migrating to D1
psql "$POSTGRES_URL" -c "\COPY chord_charts FROM 'export.csv' WITH (FORMAT csv, HEADER true);"
# Then use pg_dump -> d1 migration tooling once data is in Postgres
```

## Prevention

```typescript
// Integration test: verify chunked import handles > 1000 rows correctly
import { describe, it, expect } from 'vitest';
import { env } from 'cloudflare:test';

describe('D1 chunked import', () => {
  it('successfully imports 3000 rows in batches of 1000', async () => {
    const rows = Array.from({ length: 3000 }, (_, i) => ({
      id: `chart-${i}`,
      title: `Chart ${i}`,
      artist: 'Test Artist',
      bpm: 120,
      key: 'C',
      content: '{"chords":["C","G","Am","F"]}',
    }));

    const response = await fetch('http://localhost:8787/admin/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows }),
    });

    expect(response.status).toBe(200);
    const { inserted } = await response.json();
    expect(inserted).toBe(3000);

    const { results } = await env.DB.prepare(
      'SELECT COUNT(*) AS cnt FROM chord_charts'
    ).all();
    expect(results[0].cnt).toBe(3000);
  });
});
```

```bash
# Add to CI: dry-run migration size check before deploying
# .github/workflows/d1-migration-check.yml
# - name: Check migration file size
#   run: |
#     SIZE=$(wc -l < migrations/latest.sql)
#     if [ "$SIZE" -gt 1000 ]; then
#       echo "WARNING: Migration has $SIZE rows — use chunked import script"
#       exit 1
#     fi
```

---

## Anti-patterns

- **Single `wrangler d1 execute --file` for large SQL files** — Any file producing more than ~1000 sequential INSERTs will hit the 10-second HTTP timeout; always chunk large imports.
- **Wrapping 50k rows in a single transaction** — Even if the timeout didn't exist, a 50k-row transaction holds a write lock and can starve reads for minutes in SQLite.
- **Using D1 `batch()` with > 1000 statements** — The API rejects batches over the 1000-statement limit with an error; always split into groups of ≤1000.
- **No idempotency on insert** — If an import chunk partially succeeds before a timeout, re-running will fail with duplicate key errors unless `ON CONFLICT DO NOTHING` or `INSERT OR IGNORE` is used.
- **Treating D1 as a bulk-import target without pre-staging** — D1 is optimized for transactional reads/writes, not bulk ETL; use Postgres + COPY for initial bulk loads, then replicate to D1.

---

## Gotchas

- `wrangler d1 execute` without `--remote` runs against the local D1 emulator — always add `--remote` for production imports.
- D1 import progress is not streamed; a timeout gives no indication of how many rows were committed before failure — always use explicit transactions per chunk and track progress externally.
- D1 `batch()` executes statements in a single transaction by default; if any statement fails, the entire batch is rolled back. Use `ON CONFLICT` clauses to make inserts idempotent.
- The D1 REST API (`/import`) accepts `.sql` files directly via multipart form upload — this is what wrangler uses internally. Direct API calls have the same 10-second timeout.
- Wrangler v3+ introduced `wrangler d1 export` and `wrangler d1 import` commands (separate from `execute`) — check wrangler version; newer chunking support may be available.
- For Hyperdrive: Hyperdrive requires a Postgres connection string and is not a direct D1 replacement; it proxies Postgres connections from Workers, not SQLite.

---

## Verification

```bash
# Verify row count after chunked import completes
wrangler d1 execute orchords-db --remote \
  --command "SELECT COUNT(*) AS total FROM chord_charts;"

# Verify no duplicate IDs were inserted
wrangler d1 execute orchords-db --remote \
  --command "SELECT id, COUNT(*) AS cnt FROM chord_charts GROUP BY id HAVING cnt > 1;"

# Check for partial imports (rows with NULL required fields)
wrangler d1 execute orchords-db --remote \
  --command "SELECT COUNT(*) FROM chord_charts WHERE title IS NULL OR content IS NULL;"

# Time a 1000-row chunk import to estimate total migration duration
time wrangler d1 execute orchords-db \
  --file scratch/chunk_001.sql --remote
```

---

## Related

- `lessons-kv-write-amplification-list-keys.md`
- `lessons-workers-wasm-memory-limit.md`

---

## Sources

- Cloudflare D1 Limits — https://developers.cloudflare.com/d1/platform/limits/
- wrangler d1 execute reference — https://developers.cloudflare.com/workers/wrangler/commands/#d1
- D1 batch() API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batchstatements
- Hyperdrive documentation — https://developers.cloudflare.com/hyperdrive/
- Postgres COPY command — https://www.postgresql.org/docs/current/sql-copy.html
