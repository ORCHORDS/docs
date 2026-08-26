# Vectorize Namespace Migration and Reindex with Workers

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

Your Vectorize index was created with an older embedding model (e.g. `baai/bge-small-en-v1.5`, 384 dimensions) and you need to migrate to a higher-quality model (e.g. `baai/bge-large-en-v1.5`, 1024 dimensions). Or you need to rename an index, split a shared index into per-tenant namespaces, or rebuild after a schema change. Vectorize does not provide an in-place re-dimension operation — migration requires creating a new index, re-embedding all documents, upserting into the new index, verifying parity, then cutting traffic over.

## Context

Cloudflare Vectorize indexes are created with a fixed `dimensions` and `metric` that cannot be changed after creation. Each index supports namespaces (the `namespace` field on a vector) that act as partition filters within a single index. Migration between indexes or namespace reorganizations must be scripted via the Vectorize REST API or the `env.VECTORIZE` binding. This article covers the full migration runbook: parallel index operation, backfill Workers pipeline, query parity check, and atomic traffic cutover using a KV feature flag.

---

## 1. Create the Target Index

```bash
# Create new index with updated dimensions and metric
wrangler vectorize create my-index-v2 \
  --dimensions=1024 \
  --metric=cosine \
  --description="Migrated from bge-small 384d to bge-large 1024d"

# Bind both indexes in wrangler.toml during migration
# [[vectorize]]
# binding = "VECTORIZE_V1"
# index_name = "my-index-v1"
#
# [[vectorize]]
# binding = "VECTORIZE_V2"
# index_name = "my-index-v2"
```

---

## 2. Source Vector Export

Vectorize does not expose a native "export all vectors" endpoint. Maintain a source-of-truth document store (R2 or D1) and re-embed from there. If you only have the Vectorize index, iterate via the metadata-only list endpoint.

```typescript
// src/export-ids.ts  — list all vector IDs from source index
export async function listAllVectorIds(
  vectorize: VectorizeIndex,
  namespace?: string
): Promise<string[]> {
  const ids: string[] = [];
  let cursor: string | undefined;

  // Vectorize list uses cursor-based pagination
  // Note: As of 2026, listByIds requires known IDs; use your document store instead.
  // This example assumes IDs are stored in D1.
  return ids;
}

// Better approach: pull document IDs from your canonical store
export async function getDocumentIdsFromD1(db: D1Database): Promise<string[]> {
  const rows = await db
    .prepare('SELECT id FROM documents WHERE embedding_model = ? ORDER BY id')
    .bind('baai/bge-small-en-v1.5')
    .all<{ id: string }>();
  return rows.results.map(r => r.id);
}
```

---

## 3. Backfill Worker — Re-embed and Upsert

A Queue-driven Worker reads batches of document IDs, fetches text from the source store, generates new embeddings with the target model, and upserts into the new index.

```typescript
// src/reindex-worker.ts
export interface Env {
  AI: Ai;
  VECTORIZE_V2: VectorizeIndex;
  SOURCE_BUCKET: R2Bucket;
  DB: D1Database;
  REINDEX_QUEUE: Queue<{ batchIds: string[] }>;
}

const TARGET_MODEL = '@cf/baai/bge-large-en-v1.5';
const BATCH_SIZE = 50;

// Dispatch phase: enqueue all document IDs in batches
export async function dispatchReindex(env: Env): Promise<void> {
  const allIds = await getAllDocumentIds(env.DB);
  for (let i = 0; i < allIds.length; i += BATCH_SIZE) {
    await env.REINDEX_QUEUE.send({ batchIds: allIds.slice(i, i + BATCH_SIZE) });
  }
  console.log(`Dispatched ${Math.ceil(allIds.length / BATCH_SIZE)} batches`);
}

// Consumer: process one batch per queue message
export const queueHandler = {
  async queue(
    batch: MessageBatch<{ batchIds: string[] }>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      const { batchIds } = msg.body;
      await processReindexBatch(batchIds, env);
      msg.ack();
    }
  },
};

async function processReindexBatch(ids: string[], env: Env): Promise<void> {
  // Fetch document texts
  const docs = await Promise.all(
    ids.map(async id => {
      const obj = await env.SOURCE_BUCKET.get(`docs/${id}.txt`);
      const text = obj ? await obj.text() : null;
      return { id, text };
    })
  );

  const valid = docs.filter(d => d.text != null) as { id: string; text: string }[];
  if (valid.length === 0) return;

  // Generate embeddings with new model
  const embeddingResponse = await env.AI.run(TARGET_MODEL, {
    text: valid.map(d => d.text),
  });

  const vectors: VectorizeVector[] = valid.map((doc, i) => ({
    id: doc.id,
    values: (embeddingResponse as { data: number[][] }).data[i],
    metadata: { source: 'reindex', model: TARGET_MODEL },
  }));

  // Upsert into new index
  await env.VECTORIZE_V2.upsert(vectors);

  // Mark as migrated in D1
  const placeholders = valid.map(() => '?').join(', ');
  await env.DB
    .prepare(`UPDATE documents SET embedding_model = ?, migrated_at = datetime('now') WHERE id IN (${placeholders})`)
    .bind(TARGET_MODEL, ...valid.map(d => d.id))
    .run();
}

async function getAllDocumentIds(db: D1Database): Promise<string[]> {
  const rows = await db
    .prepare('SELECT id FROM documents WHERE migrated_at IS NULL ORDER BY id')
    .all<{ id: string }>();
  return rows.results.map(r => r.id);
}
```

---

## 4. Namespace Reorganization

If you are splitting a monolithic index into per-tenant namespaces, add the `namespace` field during upsert:

```typescript
const vectors: VectorizeVector[] = valid.map((doc, i) => ({
  id: doc.id,
  values: embeddingResponse.data[i],
  namespace: doc.tenantId,   // partition within the new index
  metadata: { tenantId: doc.tenantId, source: 'reindex' },
}));

await env.VECTORIZE_V2.upsert(vectors);
```

Query with namespace filter post-migration:

```typescript
const results = await env.VECTORIZE_V2.query(queryVector, {
  topK: 10,
  namespace: tenantId,
  returnMetadata: true,
});
```

---

## 5. Parity Check and Traffic Cutover

Before switching traffic, run a query parity check to verify result quality is equivalent or better in the new index.

```typescript
// src/parity-check.ts
export async function runParityCheck(
  v1: VectorizeIndex,
  v2: VectorizeIndex,
  ai: Ai,
  testQueries: string[]
): Promise<{ passRate: number; failures: string[] }> {
  let passed = 0;
  const failures: string[] = [];

  for (const query of testQueries) {
    const embResp = await ai.run('@cf/baai/bge-large-en-v1.5', { text: [query] });
    const v2Results = await v2.query(
      (embResp as { data: number[][] }).data[0],
      { topK: 5, returnMetadata: true }
    );

    // Simple check: top result score above threshold
    if (v2Results.matches[0]?.score >= 0.75) {
      passed++;
    } else {
      failures.push(query);
    }
  }

  return { passRate: passed / testQueries.length, failures };
}

// Atomic cutover via KV feature flag
export async function cutoverTraffic(kv: KVNamespace, targetIndex: 'v1' | 'v2'): Promise<void> {
  await kv.put('vectorize:active-index', targetIndex);
}

// In the query Worker, read the flag before each query
export async function queryWithFlag(
  kv: KVNamespace,
  v1: VectorizeIndex,
  v2: VectorizeIndex,
  vector: number[],
  namespace: string
): Promise<VectorizeMatches> {
  const activeIndex = (await kv.get('vectorize:active-index')) ?? 'v1';
  const index = activeIndex === 'v2' ? v2 : v1;
  return index.query(vector, { topK: 10, namespace, returnMetadata: true });
}
```

---

## Anti-patterns

- **Deleting the old index before verifying the new one** — always run parity checks and keep the old index live for at least one week post-cutover as a rollback target.
- **Re-embedding from Vectorize directly** — Vectorize does not expose a "get all vectors" endpoint. Maintain a canonical document store in R2 or D1 as the source of truth.
- **Upsert batches larger than 1000 vectors** — the Vectorize upsert limit per call is 1000 vectors (or 1MB payload); split into 50–100 vector batches for headroom.
- **Blocking the migration Worker on each R2 fetch** — use `Promise.all` to fetch documents in parallel, but cap concurrency to avoid R2 rate limits.
- **Switching traffic before migration completes** — track `migrated_at IS NULL` count in D1 as the progress indicator; only cut over when count reaches 0.

## Gotchas

- Vectorize `upsert` is idempotent on `id` — safe to re-run failed batches. Track progress by `migrated_at` in D1, not by guessing which batches succeeded.
- Namespace is immutable per vector after upsert; to move a vector to a different namespace, delete it by ID and re-upsert with the new namespace.
- `wrangler vectorize delete` is irreversible and immediate; there is no soft-delete or recycle bin.
- If the old and new models have different tokenizers, the same text will produce different semantic representations — do not mix vectors from different models in the same index.
- Re-indexing 100k documents via a single Worker cron invocation will hit the 30 s wall-clock limit; always use Queues for datasets larger than a few thousand documents.

## Verification

1. After dispatching reindex batches, query `SELECT COUNT(*) FROM documents WHERE migrated_at IS NULL` in D1 and watch it approach 0 over time.
2. Run `wrangler vectorize get my-index-v2 --ids=<known-id>` (or use `listByIds`) to confirm a sample vector exists in the new index.
3. Execute the parity check against 20 representative queries and assert `passRate >= 0.90`.
4. Set the KV flag to `v2`, issue #<number> live queries, and verify response shapes are identical to the v1 path.
5. Confirm the old index still returns valid results after cutover (do not delete yet).

## Related

- `vectorize-index-lifecycle-management.md`
- `vectorize-multi-tenant-namespace-partitioning.md`
- `embedding-model-migration.md`
- `vectorize-batch-upsert-incremental-sync.md`
- `workers-ai-embeddings-batch-r2.md`

## Sources

- https://developers.cloudflare.com/vectorize/
- https://developers.cloudflare.com/vectorize/reference/client-api/
- https://developers.cloudflare.com/vectorize/best-practices/
- https://developers.cloudflare.com/queues/
