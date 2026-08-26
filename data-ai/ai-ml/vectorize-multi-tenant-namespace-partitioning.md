# Vectorize Multi-Tenant Namespace Partitioning for RAG

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You are building a RAG product where multiple customers or workspaces share the same
Cloudflare Vectorize index. Retrieval must be strictly isolated per tenant — customer A
must never see chunks belonging to customer B — while keeping operational overhead low
by avoiding a separate index per tenant.

## Context

Cloudflare Vectorize supports storing arbitrary metadata alongside each vector. You can
filter queries by metadata fields, which makes it possible to partition a single index
by tenant using a `tenantId` metadata field without provisioning N separate indexes.
The trade-off is query latency versus provisioning complexity: per-index isolation is
hardest operationally but fastest; metadata filtering on a shared index is simplest but
adds a few milliseconds per query at large scale.

A hybrid approach — one index per *tier* (e.g., free / pro / enterprise) with metadata
partitioning within each tier — is the practical sweet spot for most SaaS products.

---

## 1. Embedding and Upserting with Tenant Metadata

```typescript
// src/ingest.ts
interface ChunkMeta {
  tenantId: string;
  docId: string;
  chunkIndex: number;
  source: string;
}

export async function ingestChunk(
  env: Env,
  chunk: string,
  meta: ChunkMeta
): Promise<void> {
  const embeddingRes = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: [chunk],
  });

  const vector = embeddingRes.data[0];

  await env.VECTORIZE.upsert([
    {
      id: `${meta.tenantId}::${meta.docId}::${meta.chunkIndex}`,
      values: vector,
      metadata: {
        tenantId: meta.tenantId,
        docId: meta.docId,
        chunkIndex: meta.chunkIndex,
        source: meta.source,
        text: chunk, // store text inline for retrieval without a separate KV lookup
      },
    },
  ]);
}
```

The vector ID includes `tenantId` as a prefix so you can bulk-delete a tenant's data
with a predictable ID range pattern.

---

## 2. Querying with Mandatory Tenant Filter

```typescript
// src/query.ts
export interface RetrievalResult {
  text: string;
  docId: string;
  score: number;
}

export async function retrieveForTenant(
  env: Env,
  tenantId: string,
  query: string,
  topK = 5
): Promise<RetrievalResult[]> {
  const embeddingRes = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
    text: [query],
  });

  const queryVector = embeddingRes.data[0];

  const results = await env.VECTORIZE.query(queryVector, {
    topK,
    returnMetadata: 'all',
    filter: { tenantId }, // <-- critical: always inject tenant filter
  });

  return results.matches.map((m) => ({
    text: m.metadata?.text as string,
    docId: m.metadata?.docId as string,
    score: m.score,
  }));
}
```

Never let `tenantId` come from user-controlled input without validation against a
session token. The filter is a correctness guard, not just an optimisation.

---

## 3. Tenant Onboarding and Document Deletion

```typescript
// src/tenant-lifecycle.ts

// Delete all vectors for a document (e.g., when a doc is updated)
export async function deleteDocument(
  env: Env,
  tenantId: string,
  docId: string,
  totalChunks: number
): Promise<void> {
  const ids = Array.from({ length: totalChunks }, (_, i) =>
    `${tenantId}::${docId}::${i}`
  );

  // Vectorize.deleteByIds accepts up to 1 000 ids per call
  const BATCH = 1000;
  for (let i = 0; i < ids.length; i += BATCH) {
    await env.VECTORIZE.deleteByIds(ids.slice(i, i + BATCH));
  }
}

// Purge all vectors for a tenant (GDPR right-to-erasure)
// Requires tracking chunk counts in D1 — Vectorize has no native "delete by filter"
export async function purgeTenant(
  env: Env,
  tenantId: string
): Promise<void> {
  const rows = await env.DB.prepare(
    'SELECT doc_id, chunk_count FROM documents WHERE tenant_id = ?'
  )
    .bind(tenantId)
    .all<{ doc_id: string; chunk_count: number }>();

  for (const row of rows.results) {
    await deleteDocument(env, tenantId, row.doc_id, row.chunk_count);
  }

  await env.DB.prepare('DELETE FROM documents WHERE tenant_id = ?')
    .bind(tenantId)
    .run();
}
```

---

## 4. D1 Index for Chunk Bookkeeping

```sql
-- migrations/0001_documents.sql
CREATE TABLE documents (
  tenant_id  TEXT NOT NULL,
  doc_id     TEXT NOT NULL,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (tenant_id, doc_id)
);

CREATE INDEX idx_documents_tenant ON documents (tenant_id);
```

Maintain `chunk_count` in D1 so bulk deletes can reconstruct the full vector ID list
without scanning Vectorize (which has no list-by-filter API).

---

## 5. Tier-Based Index Routing

```typescript
// src/index-router.ts
type Tier = 'free' | 'pro' | 'enterprise';

function vectorizeIndexForTier(env: Env, tier: Tier): VectorizeIndex {
  switch (tier) {
    case 'enterprise': return env.VECTORIZE_ENT;
    case 'pro':        return env.VECTORIZE_PRO;
    default:           return env.VECTORIZE_FREE;
  }
}

// In wrangler.toml, bind each index:
// [[vectorize]]
// binding = "VECTORIZE_FREE"
// index_name = "rag-free"
//
// [[vectorize]]
// binding = "VECTORIZE_PRO"
// index_name = "rag-pro"
//
// [[vectorize]]
// binding = "VECTORIZE_ENT"
// index_name = "rag-enterprise"
```

This reduces cross-tenant noise in ANN search because vectors from different tier
sizes don't compete in the same HNSW graph.

---

## Anti-patterns

- **Skipping the tenant filter** and relying solely on ID prefixes — Vectorize query
  does not filter by ID prefix; metadata filter is the only enforcement mechanism.
- **Storing tenant data in a single un-filtered index without metadata** — once indexes
  grow large, adding metadata retroactively requires a full re-upsert.
- **Deleting vectors without tracking chunk counts in a relational store** — Vectorize
  has no "query all vectors for tenant X" API, so you cannot reconstruct IDs at
  deletion time without a side-table.
- **Letting client code pass `tenantId` directly from a JWT claim without re-verifying
  the claim server-side** — always resolve `tenantId` from a validated session in the
  Worker, not from a client-supplied body parameter.

---

## Gotchas

- `filter` on Vectorize requires that the metadata field was present at upsert time;
  vectors upserted without `tenantId` will **not** appear in filtered queries, which
  creates silent data gaps rather than errors.
- Vectorize `deleteByIds` silently succeeds for IDs that do not exist — safe for
  idempotent re-runs but won't tell you if your ID reconstruction logic is wrong.
- Metadata stored inline (`text` field) counts toward the 10 KB-per-vector metadata
  limit. For chunks >8 KB, store text in R2 or KV and reference by key instead.
- Vectorize indexes have a maximum of 5 million vectors per index (as of mid-2026);
  plan tier sizing accordingly and use D1 to track per-tenant usage.

---

## Verification

```typescript
// Integration smoke test
async function smokeTestTenantIsolation(env: Env) {
  const tenantA = 'tenant-alpha';
  const tenantB = 'tenant-beta';

  await ingestChunk(env, 'Alpha secret document', {
    tenantId: tenantA, docId: 'doc1', chunkIndex: 0, source: 'test',
  });

  const resultsForB = await retrieveForTenant(env, tenantB, 'Alpha secret', 5);
  console.assert(resultsForB.length === 0, 'Tenant B must not see Tenant A vectors');

  const resultsForA = await retrieveForTenant(env, tenantA, 'Alpha secret', 5);
  console.assert(resultsForA.length > 0, 'Tenant A must see its own vectors');
}
```

---

## Related

- `cloudflare-vectorize-patterns.md`
- `retrieval-augmented-generation-d1-vectorize.md`
- `vectorize-batch-upsert-incremental-sync.md`
- `metadata-filtering-vectors.md`
- `rag-ingestion-pipeline.md`

---

## Sources

- Cloudflare Vectorize docs — metadata filtering: https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
- Cloudflare Vectorize limits: https://developers.cloudflare.com/vectorize/platform/limits/
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
