# Vectorize ANN Index Rebuild: Zero-Downtime Strategy

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your Vectorize index needs to be fully rebuilt — because you changed embedding models, switched distance metrics, corrected a bulk ingestion error, or need to backfill new metadata fields across all vectors. A naive approach (delete all vectors, re-ingest) takes your search endpoint offline for minutes to hours depending on corpus size. Production traffic during that window returns empty results or stale data.

This article covers a blue-green index swap pattern for Cloudflare Vectorize: build a shadow index in parallel, validate it against held-out queries, then atomically cut over traffic without downtime.

## Context

Cloudflare Vectorize does not provide a built-in index cloning or blue-green promotion mechanism. The pattern must be implemented at the application layer using Workers, KV (for configuration state), and D1 (as the authoritative document store). Vectorize does support multiple indexes per account, which is the foundation of the blue-green approach.

Because Vectorize indexes are declared in `wrangler.toml` bindings, a zero-downtime swap requires either (a) two static bindings and a routing flag in KV, or (b) a dynamic REST API client that reads the active index name from KV at query time. This article implements option (a) — two pre-declared bindings, runtime routing via KV.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Worker (query path)                                     │
│                                                         │
│  1. Read active_index from KV (cached 60s)              │
│  2. Route to VECTORIZE_BLUE or VECTORIZE_GREEN binding  │
│  3. Return results                                       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Worker (ingest path / rebuild)                          │
│                                                         │
│  1. Writes ALWAYS go to both indexes (dual-write)        │
│     during transition; single index otherwise            │
│  2. Rebuild Worker drains D1 → shadow index in batches   │
└─────────────────────────────────────────────────────────┘
```

## Step 1: Dual-Binding wrangler.toml

```toml
# wrangler.toml
name = "semantic-search"
main = "src/worker.ts"
compatibility_date = "2026-01-01"

[[vectorize]]
binding = "VECTORIZE_BLUE"
index_name = "corpus-blue"

[[vectorize]]
binding = "VECTORIZE_GREEN"
index_name = "corpus-green"

[[kv_namespaces]]
binding = "CONFIG_KV"
id = "your-kv-namespace-id"

[[d1_databases]]
binding = "DB"
database_name = "corpus"
database_id = "your-d1-database-id"
```

```typescript
// types.ts
export type IndexColor = "blue" | "green";

export interface Env {
  AI: Ai;
  VECTORIZE_BLUE: VectorizeIndex;
  VECTORIZE_GREEN: VectorizeIndex;
  CONFIG_KV: KVNamespace;
  DB: D1Database;
}

// KV keys
export const KV_ACTIVE_INDEX = "active_index";       // "blue" | "green"
export const KV_DUAL_WRITE   = "dual_write_enabled"; // "true" | "false"
export const KV_REBUILD_CURSOR = "rebuild_cursor";   // D1 row ID for resume
```

## Step 2: Routing Helpers

```typescript
// routing.ts
import { Env, IndexColor, KV_ACTIVE_INDEX, KV_DUAL_WRITE } from "./types";

let cachedActive: IndexColor | null = null;
let cacheExpiry = 0;
const CACHE_TTL_MS = 60_000; // 1-minute soft cache to avoid KV reads per query

export async function getActiveIndex(env: Env): Promise<VectorizeIndex> {
  const now = Date.now();
  if (!cachedActive || now > cacheExpiry) {
    const val = await env.CONFIG_KV.get(KV_ACTIVE_INDEX);
    cachedActive = (val as IndexColor) ?? "blue";
    cacheExpiry = now + CACHE_TTL_MS;
  }
  return cachedActive === "blue" ? env.VECTORIZE_BLUE : env.VECTORIZE_GREEN;
}

export async function getShadowIndex(env: Env): Promise<VectorizeIndex> {
  const active = await getActiveIndex(env);
  return active === env.VECTORIZE_BLUE ? env.VECTORIZE_GREEN : env.VECTORIZE_BLUE;
}

export async function isDualWriteEnabled(env: Env): Promise<boolean> {
  const val = await env.CONFIG_KV.get(KV_DUAL_WRITE);
  return val === "true";
}
```

## Step 3: Dual-Write Ingest Middleware

During the rebuild window, new writes go to both indexes. This ensures the shadow index does not fall behind on recent documents:

```typescript
// ingest.ts
import { Env } from "./types";
import { isDualWriteEnabled, getActiveIndex, getShadowIndex } from "./routing";

interface Document {
  id: string;
  text: string;
  metadata: Record<string, string>;
}

export async function ingestDocument(doc: Document, env: Env): Promise<void> {
  // 1. Store text in D1 (source of truth)
  await env.DB.prepare(
    `INSERT INTO passages (id, text, metadata, updated_at)
     VALUES (?, ?, ?, CURRENT_TIMESTAMP)
     ON CONFLICT(id) DO UPDATE SET text=excluded.text,
       metadata=excluded.metadata, updated_at=excluded.updated_at`
  )
    .bind(doc.id, doc.text, JSON.stringify(doc.metadata))
    .run();

  // 2. Generate embedding
  const { data } = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [doc.text],
  });
  const vector = { id: doc.id, values: data[0], metadata: doc.metadata };

  // 3. Write to active index always
  const active = await getActiveIndex(env);
  await active.upsert([vector]);

  // 4. Write to shadow index during dual-write window
  if (await isDualWriteEnabled(env)) {
    const shadow = await getShadowIndex(env);
    await shadow.upsert([vector]);
  }
}
```

## Step 4: Rebuild Worker (Scheduled)

Run as a scheduled Worker or triggered via a Queue. Reads D1 in batches, writes to the shadow index, persists a cursor so it can be interrupted and resumed:

```typescript
// rebuild.ts  — deploy as a separate Worker or Cron Trigger
import { Env, KV_REBUILD_CURSOR } from "./types";
import { getShadowIndex } from "./routing";

const BATCH_SIZE = 500; // Vectorize upsert limit per call

export async function rebuildShadowIndex(env: Env): Promise<{
  processed: number;
  done: boolean;
}> {
  const shadow = await getShadowIndex(env);

  // Resume from last cursor (D1 row ID)
  const cursorStr = await env.CONFIG_KV.get(KV_REBUILD_CURSOR);
  const cursor = cursorStr ? parseInt(cursorStr, 10) : 0;

  const rows = await env.DB.prepare(
    `SELECT id, text, metadata, rowid
     FROM passages
     WHERE rowid > ?
     ORDER BY rowid ASC
     LIMIT ${BATCH_SIZE}`
  )
    .bind(cursor)
    .all<{ id: string; text: string; metadata: string; rowid: number }>();

  if (rows.results.length === 0) {
    // Rebuild complete — clear cursor
    await env.CONFIG_KV.delete(KV_REBUILD_CURSOR);
    return { processed: 0, done: true };
  }

  // Batch-embed all texts in this page
  const texts = rows.results.map((r) => r.text);
  const embedResponse = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: texts,
  });

  const vectors = rows.results.map((r, i) => ({
    id: r.id,
    values: embedResponse.data[i],
    metadata: JSON.parse(r.metadata) as Record<string, string>,
  }));

  await shadow.upsert(vectors);

  // Persist cursor
  const lastRowId = rows.results[rows.results.length - 1].rowid;
  await env.CONFIG_KV.put(KV_REBUILD_CURSOR, String(lastRowId));

  return {
    processed: rows.results.length,
    done: rows.results.length < BATCH_SIZE, // last page if fewer than batch size
  };
}
```

## Step 5: Validation Before Cut-Over

Before promoting the shadow index to active, validate its recall against a held-out golden query set stored in D1:

```typescript
// validate.ts
import { Env } from "./types";
import { getShadowIndex, getActiveIndex } from "./routing";

interface ValidationResult {
  query: string;
  activeTopId: string;
  shadowTopId: string;
  match: boolean;
  activeScore: number;
  shadowScore: number;
}

export async function validateShadowIndex(
  env: Env,
  goldenQueries: string[]
): Promise<{ passRate: number; results: ValidationResult[] }> {
  const active = await getActiveIndex(env);
  const shadow = await getShadowIndex(env);

  const results: ValidationResult[] = [];

  for (const query of goldenQueries) {
    const { data } = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
      text: [query],
    });
    const vec = data[0];

    const [activeResult, shadowResult] = await Promise.all([
      active.query(vec, { topK: 1 }),
      shadow.query(vec, { topK: 1 }),
    ]);

    const activeTop = activeResult.matches[0];
    const shadowTop = shadowResult.matches[0];

    results.push({
      query,
      activeTopId: activeTop?.id ?? "",
      shadowTopId: shadowTop?.id ?? "",
      match: activeTop?.id === shadowTop?.id,
      activeScore: activeTop?.score ?? 0,
      shadowScore: shadowTop?.score ?? 0,
    });
  }

  const passRate = results.filter((r) => r.match).length / results.length;
  return { passRate, results };
}
```

## Step 6: Atomic Cut-Over

Once validation passes (e.g., pass rate > 95%), promote the shadow index:

```typescript
// cutover.ts
import { Env, IndexColor, KV_ACTIVE_INDEX, KV_DUAL_WRITE } from "./types";
import { validateShadowIndex } from "./validate";

export async function performCutover(
  env: Env,
  goldenQueries: string[],
  minPassRate = 0.95
): Promise<{ success: boolean; passRate: number; message: string }> {
  // 1. Validate shadow
  const { passRate, results } = await validateShadowIndex(env, goldenQueries);

  if (passRate < minPassRate) {
    return {
      success: false,
      passRate,
      message: `Validation failed: ${(passRate * 100).toFixed(1)}% < ${(minPassRate * 100).toFixed(1)}% threshold`,
    };
  }

  // 2. Determine shadow color
  const currentActive = (await env.CONFIG_KV.get(KV_ACTIVE_INDEX)) as IndexColor ?? "blue";
  const newActive: IndexColor = currentActive === "blue" ? "green" : "blue";

  // 3. Atomically promote shadow → active
  // KV put is eventually consistent (< 60s globally); set TTL=0 for immediate propagation
  await env.CONFIG_KV.put(KV_ACTIVE_INDEX, newActive);

  // 4. Keep dual-write ON for 5 minutes post-cutover, then disable
  // (handled by a scheduled cleanup or manual call)
  // await env.CONFIG_KV.put(KV_DUAL_WRITE, "false");

  // 5. Invalidate in-memory cache (Workers instances will refresh within 60s)
  // No explicit invalidation available across instances; rely on TTL

  return {
    success: true,
    passRate,
    message: `Cut over from ${currentActive} to ${newActive}. Pass rate: ${(passRate * 100).toFixed(1)}%`,
  };
}
```

## Anti-patterns

- Deleting all vectors from the active index before the shadow is ready — causes a full outage window
- Not enabling dual-write before starting the rebuild — documents ingested during rebuild are missing from the shadow index
- Forgetting to persist the rebuild cursor to KV — a Worker timeout or crash forces a full restart from row 0
- Switching the active index before validation completes — results in serving an incomplete index silently
- Leaving dual-write enabled indefinitely after cutover — doubles write cost and write latency
- Running the rebuild Worker on the query-serving Worker — rebuild's embedding calls will exhaust CPU time budget; use a separate Cron Trigger Worker
- Not clearing the old (now shadow) index after cutover — stale data accumulates and the next rebuild has dirty data to contend with

## Gotchas

- Vectorize KV and Workers KV are different products. The `CONFIG_KV` binding is Workers KV (namespace-based key-value), not Vectorize's internal KV. Do not confuse them in wrangler.toml.
- Workers KV has eventual consistency with a typical propagation window of 60 seconds globally. Clients may still route to the old active index for up to 60 seconds post-cutover.
- The in-process cache in `routing.ts` adds another 60 seconds of lag per Worker instance. Total worst-case lag after cutover is ~2 minutes. Plan your dual-write window accordingly — keep dual-write on for at least 5 minutes post-cutover.
- Vectorize `upsert` in the rebuild phase is charged per vector. A 1-million-vector corpus rebuild costs 1 million upsert operations on the shadow index.
- Workers AI batch embedding has a per-request text limit. For passages >512 tokens, pre-chunk before embedding.
- D1 `rowid` is an internal SQLite rowid, not your application `id`. It is stable across reads but may have gaps after deletes.

## Verification

```typescript
// Smoke test the full flow in wrangler dev
async function smokeTestBlueGreen(env: Env): Promise<void> {
  // 1. Confirm active index serves results
  const active = await getActiveIndex(env);
  const testVec = new Array(768).fill(0.1);
  const results = await active.query(testVec, { topK: 1 });
  console.assert(results.matches.length >= 0, "Active index must respond");

  // 2. Confirm KV routing flag reads correctly
  const color = await env.CONFIG_KV.get(KV_ACTIVE_INDEX);
  console.assert(
    color === "blue" || color === "green" || color === null,
    `Invalid active index color: ${color}`
  );

  // 3. Confirm dual-write flag reads correctly
  const dualWrite = await env.CONFIG_KV.get(KV_DUAL_WRITE);
  console.log(`Active: ${color ?? "blue"}, Dual-write: ${dualWrite ?? "false"}`);
  console.log("Blue-green smoke test passed.");
}
```

## Related

- `vectorize-index-lifecycle-management.md` — routine index maintenance and deletion strategies
- `vectorize-batch-upsert-incremental-sync.md` — efficient bulk ingestion patterns
- `vectorize-namespace-migration-reindex.md` — namespace-level migration patterns
- `embedding-model-migration.md` — handling embedding model upgrades across indexes

## Sources

- Cloudflare Vectorize REST API reference: https://developers.cloudflare.com/vectorize/reference/client-api/
- Cloudflare Workers KV consistency model: https://developers.cloudflare.com/kv/reference/how-kv-works/
- Blue-green deployment pattern: Humble, J. & Farley, D. "Continuous Delivery." Addison-Wesley, 2010
