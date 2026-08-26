# Vectorize Index Lifecycle Management

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Your Vectorize index grows stale, accumulates deleted vectors, or needs re-indexing after an embedding model upgrade. You need a repeatable lifecycle strategy for creating, populating, backing up, migrating, and retiring indexes without downtime.

## Context
Cloudflare Vectorize indexes are tied to a specific embedding model dimension and distance metric set at creation time. Changing either requires creating a new index and re-ingesting all vectors. Because there is no built-in snapshot API, backup and migration must be orchestrated from a Worker using the REST API or bindings. A blue/green index swap pattern eliminates downtime during re-indexing.

## Creating an Index with Correct Dimensions

Always declare dimensions and metric at creation time — these cannot be changed later. Match dimensions to your embedding model output exactly.

```typescript
// src/lifecycle/create-index.ts
interface Env {
  VECTORIZE: Vectorize;
}

export async function createIndexViaAPI(
  accountId: string,
  apiToken: string,
  indexName: string,
  dimensions: number,
  metric: 'cosine' | 'euclidean' | 'dot-product'
): Promise<void> {
  const response = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/vectorize/v2/indexes`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name: indexName, config: { dimensions, metric } }),
    }
  );
  if (!response.ok) {
    const err = await response.json<{ errors: { message: string }[] }>();
    throw new Error(`Create index failed: ${err.errors[0]?.message}`);
  }
}
```

## Bulk Upsert with Chunking

Vectorize accepts at most 1,000 vectors per upsert call. Chunk large datasets and fan out via Queues to avoid hitting CPU time limits.

```typescript
// src/lifecycle/bulk-upsert.ts
interface VectorRecord {
  id: string;
  values: number[];
  metadata: Record<string, string | number | boolean>;
  namespace?: string;
}

async function bulkUpsert(
  vectorize: Vectorize,
  records: VectorRecord[],
  chunkSize = 500
): Promise<void> {
  for (let i = 0; i < records.length; i += chunkSize) {
    const chunk = records.slice(i, i + chunkSize);
    const mutation = await vectorize.upsert(chunk);
    if (mutation.mutationId) {
      // Store mutationId in KV to track async indexing completion
      console.log(`Upserted chunk ${i}–${i + chunk.length}: ${mutation.mutationId}`);
    }
    // Brief yield between large chunks to avoid subrequest stacking
    await scheduler.wait(50);
  }
}
```

## Waiting for Mutation Propagation

Vectorize indexes are eventually consistent. A vector upserted is not immediately queryable. Poll the mutation status before considering ingestion complete.

```typescript
// src/lifecycle/await-mutation.ts
async function awaitMutation(
  accountId: string,
  apiToken: string,
  indexName: string,
  mutationId: string,
  maxRetries = 30
): Promise<boolean> {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${accountId}/vectorize/v2/indexes/${indexName}/mutation-status?mutationId=${mutationId}`,
      { headers: { Authorization: `Bearer ${apiToken}` } }
    );
    const body = await res.json<{ result: { status: string } }>();
    if (body.result.status === 'COMPLETE') return true;
    if (body.result.status === 'FAILED') throw new Error(`Mutation ${mutationId} failed`);
    await scheduler.wait(2000);
  }
  return false;
}
```

## Blue/Green Index Swap for Zero-Downtime Migration

Keep two indexes active during re-indexing. Route reads to the old index until the new one is fully populated, then atomically switch via a KV flag.

```typescript
// src/lifecycle/blue-green-swap.ts
interface Env {
  VECTORIZE_BLUE: Vectorize;
  VECTORIZE_GREEN: Vectorize;
  CONFIG: KVNamespace;
}

export async function getActiveIndex(env: Env): Promise<Vectorize> {
  const active = await env.CONFIG.get('vectorize:active');
  return active === 'green' ? env.VECTORIZE_GREEN : env.VECTORIZE_BLUE;
}

export async function swapToGreen(env: Env): Promise<void> {
  // Validate green index has expected vector count before swapping
  const info = await env.VECTORIZE_GREEN.describe();
  const expected = Number(await env.CONFIG.get('vectorize:expected-count') ?? '0');
  if (info.vectorsCount < expected * 0.99) {
    throw new Error(`Green index has only ${info.vectorsCount}/${expected} vectors`);
  }
  await env.CONFIG.put('vectorize:active', 'green');
}
```

## Backup Vectors to R2

Export all vector IDs and metadata to R2 before index deletion or model migrations. Values (float arrays) are large — store them in a columnar NDJSON format.

```typescript
// src/lifecycle/backup-to-r2.ts
interface Env {
  VECTORIZE: Vectorize;
  BACKUP_BUCKET: R2Bucket;
}

export async function backupIndexToR2(env: Env, indexName: string): Promise<string> {
  const date = new Date().toISOString().slice(0, 10);
  const key = `backups/${indexName}/${date}/metadata.ndjson`;

  // Vectorize list returns up to 100 IDs per call; paginate with cursor
  let cursor: string | undefined;
  const lines: string[] = [];

  do {
    const page = await env.VECTORIZE.list({ limit: 100, cursor });
    for (const vec of page.vectors) {
      lines.push(JSON.stringify({ id: vec.id, metadata: vec.metadata, namespace: vec.namespace }));
    }
    cursor = page.done ? undefined : page.cursor;
  } while (cursor);

  await env.BACKUP_BUCKET.put(key, lines.join('\n'), {
    httpMetadata: { contentType: 'application/x-ndjson' },
  });
  return key;
}
```

## Deleting Stale Vectors by Namespace

Use namespace scoping to isolate tenant data. Delete entire namespaces when offboarding a tenant rather than scanning all vectors.

```typescript
// src/lifecycle/delete-namespace.ts
async function deleteByNamespace(
  vectorize: Vectorize,
  namespace: string
): Promise<number> {
  let deleted = 0;
  let cursor: string | undefined;

  do {
    const page = await vectorize.list({ limit: 100, namespace, cursor });
    const ids = page.vectors.map((v) => v.id);
    if (ids.length > 0) {
      await vectorize.deleteByIds(ids);
      deleted += ids.length;
    }
    cursor = page.done ? undefined : page.cursor;
  } while (cursor);

  return deleted;
}
```

## Anti-patterns
- Creating an index without specifying dimensions — defaults may not match your model output
- Upsertng >1,000 vectors in a single call — silently truncated or errored
- Querying immediately after upsert without awaiting mutation propagation — returns stale results
- Storing embedding float arrays in KV instead of keeping them in the source system for re-indexing
- Deleting an index with no backup when it is the only copy of derived embeddings

## Gotchas
- `vectorize.describe()` returns `vectorsCount` reflecting successfully indexed vectors, which lags behind upsert by seconds to minutes
- Namespace filtering is exact-match only — no prefix or wildcard support
- A blue/green swap requires two Vectorize bindings in `wrangler.jsonc`; each binding counts toward account index limits
- The Vectorize REST API requires an account-level API token with the `Vectorize:Edit` permission
- Deleting by ID is idempotent but bulk deletes are capped at 1,000 IDs per call

## Verification
1. After upsert, call `vectorize.describe()` in a loop until `vectorsCount` reaches the expected value.
2. Run a semantic query against known vectors and confirm top result has cosine score > 0.95.
3. After a blue/green swap, issue #<number> queries against both indexes and diff results — overlap should be >99%.
4. Restore a backup from R2 to a scratch index, run the same query set, compare scores.

## Related
- [Cloudflare Vectorize Patterns](cloudflare-vectorize-patterns.md)
- [Vector Embeddings D1 Vectorize Search](vector-embeddings-d1-vectorize-search.md)
- [Embedding Model Migration](embedding-model-migration.md)
- [Workers AI Embeddings Batch R2](workers-ai-embeddings-batch-r2.md)

## Sources
- https://developers.cloudflare.com/vectorize/reference/client-api/
- https://developers.cloudflare.com/vectorize/best-practices/insert-vectors/
- https://developers.cloudflare.com/vectorize/reference/client-api/#list-vectors
