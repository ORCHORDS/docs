# D1 Export to R2 Parquet for Analytics

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You accumulate event or metrics data in D1 and want to run analytical queries — aggregations, JOINs across millions of rows, time-series analysis — that are too slow or too large for D1's 10 GB limit and OLTP query model. You need a Worker pipeline that exports D1 tables to R2 as Parquet files for consumption by Athena, DuckDB, BigQuery, or R2 Data Catalog.

## Context

D1 is optimized for OLTP workloads. For analytics at scale, the standard pattern is periodic export: a Cron Trigger Worker reads D1 in cursor-paginated batches, serializes rows to Parquet using a WASM-compiled Parquet writer (e.g., `parquet-wasm`), and uploads the resulting file to R2. The R2 Data Catalog can then register the Parquet files as an Iceberg table, enabling DuckDB or Athena queries directly against R2. This avoids running complex analytics on D1 and frees the D1 instance for writes.

## Cursor-Paginated D1 Read

```typescript
const PAGE_SIZE = 5_000;

export async function* paginateD1<T>(
  db: D1Database,
  table: string,
  orderBy: string = "id"
): AsyncGenerator<T[]> {
  let lastId: string | number | null = null;

  while (true) {
    const stmt = lastId === null
      ? db.prepare(`SELECT * FROM ${table} ORDER BY ${orderBy} ASC LIMIT ?`).bind(PAGE_SIZE)
      : db.prepare(`SELECT * FROM ${table} WHERE ${orderBy} > ? ORDER BY ${orderBy} ASC LIMIT ?`).bind(lastId, PAGE_SIZE);

    const { results } = await stmt.all<T & { id: string | number }>();
    if (results.length === 0) break;

    yield results as T[];
    lastId = results[results.length - 1].id;

    if (results.length < PAGE_SIZE) break; // last page
  }
}
```

## Building a Parquet File in a Worker

```typescript
// Uses parquet-wasm compiled for the Workers runtime
// Install: npm install parquet-wasm
import initParquet, { writeParquet, ParquetWriter, Schema } from "parquet-wasm";

export async function buildParquet(rows: Record<string, unknown>[]): Promise<Uint8Array> {
  await initParquet(); // initialize WASM once per isolate lifecycle

  const schema = new Schema([
    { name: "id", type: "INT64", nullable: false },
    { name: "event_type", type: "UTF8", nullable: true },
    { name: "payload", type: "UTF8", nullable: true },
    { name: "created_at", type: "INT64", nullable: false }, // epoch ms
  ]);

  const writer = new ParquetWriter(schema, { compression: "SNAPPY" });
  writer.writeRows(rows);
  return writer.close(); // returns Uint8Array
}
```

## Cron Trigger Export Worker

```typescript
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(exportTable(env, "events"));
  },
} satisfies ExportedHandler<Env>;

async function exportTable(env: Env, table: string): Promise<void> {
  const allRows: Record<string, unknown>[] = [];

  for await (const page of paginateD1(env.DB, table, "id")) {
    allRows.push(...page);
  }

  if (allRows.length === 0) {
    console.log(`[export] ${table}: no rows`);
    return;
  }

  const parquetBytes = await buildParquet(allRows);
  const date = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const key = `exports/${table}/date=${date}/${table}_${Date.now()}.parquet`;

  await env.EXPORT_BUCKET.put(key, parquetBytes, {
    httpMetadata: { contentType: "application/octet-stream" },
    customMetadata: { table, rowCount: String(allRows.length), exportedAt: new Date().toISOString() },
  });

  console.log(`[export] uploaded ${key} (${allRows.length} rows, ${parquetBytes.byteLength} bytes)`);
}

interface Env {
  DB: D1Database;
  EXPORT_BUCKET: R2Bucket;
}
```

## Incremental Export with High-Water Mark in KV

```typescript
export async function incrementalExport(env: Env, table: string): Promise<void> {
  const hwmKey = `d1_export_hwm:${table}`;
  const hwm = await env.KV.get(hwmKey); // last exported id
  const lastId = hwm ? parseInt(hwm, 10) : 0;

  const { results: rows } = await env.DB
    .prepare(`SELECT * FROM ${table} WHERE id > ? ORDER BY id ASC LIMIT 50000`)
    .bind(lastId)
    .all<{ id: number; [key: string]: unknown }>();

  if (rows.length === 0) return;

  const parquetBytes = await buildParquet(rows);
  const key = `exports/${table}/incremental/${Date.now()}.parquet`;
  await env.EXPORT_BUCKET.put(key, parquetBytes);

  const newHwm = rows[rows.length - 1].id;
  await env.KV.put(hwmKey, String(newHwm));
  console.log(`[incremental] exported ${rows.length} rows, new HWM: ${newHwm}`);
}
```

## Registering Files with R2 Data Catalog

```typescript
// After export, call R2 Data Catalog API to add the Parquet file to an Iceberg table
export async function registerWithDataCatalog(
  env: Env,
  r2Key: string,
  table: string
): Promise<void> {
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/r2/buckets/${env.BUCKET_NAME}/catalog/tables/${table}/files`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ objectKey: r2Key, format: "parquet" }),
    }
  );

  if (!resp.ok) throw new Error(`Catalog registration failed: ${await resp.text()}`);
}
```

## Anti-patterns

- Loading all D1 rows into memory at once before writing Parquet — for tables with millions of rows this exceeds the Worker's 128 MB memory limit; stream in pages and flush Parquet row groups periodically.
- Exporting the entire table on every Cron run — use incremental high-water mark exports after the initial full dump.
- Using `TEXT` for timestamps in D1 and writing them as strings to Parquet — convert to epoch INT64 so analytical engines can use native date functions.
- Putting all exports under a flat R2 prefix — Hive-style partitioning (`date=YYYY-MM-DD/`) enables partition pruning in Athena and DuckDB.

## Gotchas

- `parquet-wasm` requires WASM support; set `compatibility_date = "2024-09-23"` or later and confirm `wasm_modules` is not restricted in your wrangler config.
- Workers have a 6-second CPU time limit on the Standard tier; large table exports must use `ctx.waitUntil()` on the Unbound tier or break work into multiple Cron runs with KV high-water marks.
- R2 `put()` is limited to ~5 GB per single-part upload; for very large Parquet files use multipart upload (`createMultipartUpload`).
- D1 `all()` returns at most 10,000 rows per call; the pagination generator above is required for larger tables.
- R2 Data Catalog is only available with R2 Data Catalog enabled on the bucket — check bucket settings before calling the registration API.

## Verification

```bash
# List exported Parquet files
wrangler r2 object list EXPORT_BUCKET --prefix "exports/events/" | jq '.[].key'

# Inspect a Parquet file with DuckDB
duckdb -c "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM read_parquet('s3://my-bucket/exports/events/date=2026-08-23/*.parquet');"

# Check row count vs D1 source
wrangler d1 execute MY_DB --command "SELECT COUNT(*) FROM events;"
```

## Related

- `d1-export-import.md` — wrangler CLI export to SQLite format
- `r2-data-catalog-compaction-snapshot-expiration.md` — Iceberg table management in R2
- `cloudflare-r2-object-lifecycle-multipart.md` — large file upload patterns
- `workers-unbound-cpu-time-management.md` — CPU time budget for heavy Workers
- `cloudflare-workers-cron-triggers-scheduling.md` — scheduling periodic exports

## Sources

- https://developers.cloudflare.com/d1/build-with-d1/export-import-data/
- https://developers.cloudflare.com/r2/data-catalog/
- https://github.com/kylebarron/parquet-wasm
- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
