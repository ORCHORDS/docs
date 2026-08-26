# Vectorize Batch Upsert and Incremental Sync

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
You have tens of thousands of documents to embed and index in Cloudflare Vectorize, but naively iterating and upserting one vector at a time saturates request budgets and takes hours. You also need new or updated documents to appear in search within minutes without re-indexing the entire corpus.

## Context
Vectorize accepts batch upserts of up to 1,000 vectors per call and has per-account mutation rate limits. The efficient pattern is to fan out embedding generation across Cloudflare Queues, collect vectors in memory, and flush them in max-size batches. Incremental sync tracks document fingerprints (content hashes) in D1 so only changed documents trigger re-embedding, keeping mutation volume proportional to actual change rate rather than corpus size.

## Batch Upsert Helper

Never upsert vectors one at a time. Accumulate into chunks of 1,000 and flush in parallel with a concurrency cap to stay within rate limits.

```typescript
// src/vectorize-batch.ts
const VECTORIZE_BATCH_SIZE = 1000;
const UPSERT_CONCURRENCY  = 3;

interface VectorRecord {
  id: string;
  values: number[];
  metadata?: Record<string, string | number | boolean>;
  namespace?: string;
}

async function batchUpsert(
  index: VectorizeIndex,
  vectors: VectorRecord[]
): Promise<{ inserted: number; mutationId: string[] }> {
  const batches: VectorRecord[][] = [];

  for (let i = 0; i < vectors.length; i += VECTORIZE_BATCH_SIZE) {
    batches.push(vectors.slice(i, i + VECTORIZE_BATCH_SIZE));
  }

  const mutationIds: string[] = [];
  let inserted = 0;

  // Process batches with bounded concurrency
  for (let i = 0; i < batches.length; i += UPSERT_CONCURRENCY) {
    const window = batches.slice(i, i + UPSERT_CONCURRENCY);
    const results = await Promise.all(
      window.map((batch) => index.upsert(batch))
    );
    for (const r of results) {
      mutationIds.push(r.mutationId);
      inserted += r.count;
    }
  }

  return { inserted, mutationIds };
}

export { batchUpsert, type VectorRecord };
```

## Document Fingerprinting with D1

Track content hashes in D1 to detect changes. Only documents whose hash differs from the stored value need re-embedding.

```typescript
// src/sync-tracker.ts
import { createHash } from "node:crypto"; // available in Workers runtime

function contentHash(text: string): string {
  // Workers runtime supports SubtleCrypto — use it for portability
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  // Fallback: fast FNV-like hash when crypto.subtle not in scope
  let h = 2166136261;
  for (const b of data) { h ^= b; h = Math.imul(h, 16777619) >>> 0; }
  return h.toString(16).padStart(8, "0");
}

interface DocRecord {
  id:          string;
  contentHash: string;
  updatedAt:   number;
}

async function getChangedDocuments(
  db: D1Database,
  documents: Array<{ id: string; content: string }>
): Promise<Array<{ id: string; content: string }>> {
  if (documents.length === 0) return [];

  const ids = documents.map((d) => d.id);
  const placeholders = ids.map(() => "?").join(",");

  const { results } = await db
    .prepare(`SELECT id, content_hash FROM vector_sync WHERE id IN (${placeholders})`)
    .bind(...ids)
    .all<DocRecord>();

  const storedHashes = new Map(results.map((r) => [r.id, r.contentHash]));

  return documents.filter((doc) => {
    const hash = contentHash(doc.content);
    return storedHashes.get(doc.id) !== hash;
  });
}

async function markDocumentsSynced(
  db: D1Database,
  documents: Array<{ id: string; content: string }>
): Promise<void> {
  const now = Date.now();
  const stmts = documents.map((doc) =>
    db
      .prepare(
        `INSERT INTO vector_sync (id, content_hash, updated_at)
         VALUES (?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET content_hash = excluded.content_hash, updated_at = excluded.updated_at`
      )
      .bind(doc.id, contentHash(doc.content), now)
  );

  // D1 batch for atomic multi-row upsert
  await db.batch(stmts);
}

export { getChangedDocuments, markDocumentsSynced };
```

## Queue-Driven Embedding Pipeline

Use Cloudflare Queues to decouple document ingestion from embedding. The producer enqueues document IDs; the consumer fetches content, embeds, and upserts.

```typescript
// src/index.ts  (producer + consumer in same Worker)
import { batchUpsert, type VectorRecord } from "./vectorize-batch";
import { getChangedDocuments, markDocumentsSynced } from "./sync-tracker";

interface Env {
  AI:        Ai;
  VECTORIZE: VectorizeIndex;
  DB:        D1Database;
  EMBED_QUEUE: Queue<{ docIds: string[] }>;
  DOCS_KV:   KVNamespace; // source of truth for document content
}

// Producer: called by a Cron Trigger or webhook
export async function ingestDocuments(env: Env, docIds: string[]): Promise<void> {
  // Fan out in batches of 100 doc IDs per queue message to stay under 128KB message limit
  for (let i = 0; i < docIds.length; i += 100) {
    await env.EMBED_QUEUE.send({ docIds: docIds.slice(i, i + 100) });
  }
}

// Consumer: processes queue batches
export default {
  async queue(batch: MessageBatch<{ docIds: string[] }>, env: Env): Promise<void> {
    const allDocIds = batch.messages.flatMap((m) => m.body.docIds);

    // Fetch document content from KV
    const docs = (
      await Promise.all(
        allDocIds.map(async (id) => {
          const content = await env.DOCS_KV.get(id);
          return content ? { id, content } : null;
        })
      )
    ).filter((d): d is { id: string; content: string } => d !== null);

    // Filter to only changed documents
    const changed = await getChangedDocuments(env.DB, docs);

    if (changed.length === 0) {
      batch.ackAll();
      return;
    }

    // Embed in sub-batches of 100 (Workers AI embedding limit)
    const vectors: VectorRecord[] = [];

    for (let i = 0; i < changed.length; i += 100) {
      const chunk = changed.slice(i, i + 100);
      const embeddingResult = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
        text: chunk.map((d) => d.content),
      });

      for (let j = 0; j < chunk.length; j++) {
        vectors.push({
          id:     chunk[j].id,
          values: embeddingResult.data[j],
          metadata: { syncedAt: Date.now() },
        });
      }
    }

    // Batch upsert to Vectorize
    await batchUpsert(env.VECTORIZE, vectors);

    // Record sync state in D1
    await markDocumentsSynced(env.DB, changed);

    batch.ackAll();
  },
};
```

## Monitoring Sync Lag with Analytics Engine

```typescript
interface Env {
  ANALYTICS: AnalyticsEngineDataset;
}

function recordSyncMetrics(
  env: Env,
  docsConsidered: number,
  docsChanged: number,
  vectorsUpserted: number,
  durationMs: number
) {
  env.ANALYTICS.writeDataPoint({
    blobs:   ["vectorize_sync"],
    doubles: [docsConsidered, docsChanged, vectorsUpserted, durationMs],
    indexes: ["sync"],
  });
}
```

## D1 Schema Bootstrap

```sql
-- Run once via wrangler d1 execute
CREATE TABLE IF NOT EXISTS vector_sync (
  id           TEXT    PRIMARY KEY,
  content_hash TEXT    NOT NULL,
  updated_at   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vector_sync_updated ON vector_sync (updated_at);
```

## Anti-patterns
- Upserting one vector per Workers fetch — each upsert is a round-trip to Vectorize; batches of 1,000 are 1,000x more efficient
- Re-embedding unchanged documents on every sync run — wastes AI inference budget and hits mutation rate limits
- Ignoring `mutationId` from upsert responses — needed to track which batches have propagated before querying
- Using a single queue consumer for large corpora — concurrency is bounded by queue batch size; shard by namespace or document type
- Storing raw embeddings in D1 instead of Vectorize — D1 is not an ANN index; cosine similarity queries over D1 BLOB columns are O(n)

## Gotchas
- Vectorize mutations are not immediately queryable — there is a propagation delay (typically seconds, up to a minute under load); poll with the `mutationId` API to confirm before serving search results
- Workers AI embedding endpoint accepts a maximum of 100 texts per call for `bge-base-en-v1.5`; larger batches return a 400 error
- D1 `batch()` is limited to 1,000 statements per call — chunk `markDocumentsSynced` if syncing more than 1,000 docs at once
- Queue consumer timeouts (30s for Workers free, 15 min for paid) must accommodate the full embed+upsert cycle for the batch size
- `contentHash` collisions are astronomically unlikely with a 32-bit FNV hash but not impossible — use SHA-256 via `crypto.subtle.digest` for production workloads

## Verification
```bash
# Create D1 table
wrangler d1 execute MY_DB --file=schema.sql

# Trigger ingestion and watch queue drain
wrangler dev --remote &
curl -X POST http://localhost:8787/ingest \
  -H "Content-Type: application/json" \
  -d '{"docIds":["doc-1","doc-2","doc-3"]}'

# Confirm vectors were upserted
wrangler vectorize get-vectors MY_INDEX --id doc-1

# Confirm sync state in D1
wrangler d1 execute MY_DB --command="SELECT id, content_hash, datetime(updated_at/1000,'unixepoch') FROM vector_sync LIMIT 10"
```

## Related
- [cloudflare-vectorize-patterns.md](cloudflare-vectorize-patterns.md)
- [vectorize-index-lifecycle-management.md](vectorize-index-lifecycle-management.md)
- [embedding-batching.md](embedding-batching.md)
- [rag-ingestion-pipeline.md](rag-ingestion-pipeline.md)
- [workers-ai-embeddings-batch-r2.md](workers-ai-embeddings-batch-r2.md)

## Sources
- Cloudflare Vectorize upsert API: https://developers.cloudflare.com/vectorize/reference/client-api/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
