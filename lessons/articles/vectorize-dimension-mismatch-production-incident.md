# Vectorize Dimension Mismatch Production Incident

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

After a planned upgrade of the embedding model used to populate a Vectorize index, all vector similarity queries began returning zero results instead of ranked matches. The semantic search feature on the platform returned empty result sets for 100% of queries for approximately 47 minutes. No error was thrown by the Vectorize API—queries succeeded with HTTP 200 but returned an empty `matches` array.

## Context

Cloudflare Vectorize indexes are created with a fixed number of dimensions specified at creation time. The index cannot be altered after creation; the dimension count is immutable for the lifetime of the index. The platform's Vectorize index was created with 768 dimensions to match the `@cf/baai/bge-base-en-v1.5` embedding model. A decision was made to upgrade to `@cf/baai/bge-large-en-v1.5`, which produces 1024-dimensional embeddings, to improve recall quality. The migration plan included re-indexing all vectors but incorrectly assumed that inserting 1024-dimensional vectors into a 768-dimensional index would throw an explicit error. Instead, Vectorize silently truncated or rejected the inserts without surfacing an error in the upsert response, leaving the index populated with a mix of old 768-dimension vectors (which were deleted during migration) and zero valid vectors.

## Timeline

- **14:00 UTC** — Migration script begins deleting existing vectors from the 768-dimensional index in batches.
- **14:08 UTC** — All 2.1 million vectors deleted; index is now empty.
- **14:09 UTC** — Migration script begins upserting 1024-dimensional vectors from the new model into the same 768-dimensional index.
- **14:10 UTC** — First user reports of empty search results; semantic search feature returns zero matches for all queries.
- **14:11 UTC** — Monitoring alert fires: `semantic_search_results_p50` drops from 8 to 0.
- **14:15 UTC** — On-call begins triage; Worker logs show no errors; Vectorize upsert calls return 200 OK.
- **14:31 UTC** — Vectorize index inspected via API; `vectorCount` shows 0 despite 200 OK upsert responses.
- **14:38 UTC** — Root cause identified: 1024-dimensional vectors cannot be upserted into a 768-dimensional index; inserts are silently discarded.
- **14:47 UTC** — Decision made to create a new 1024-dimensional index and re-ingest; migration script re-run against new index.
- **15:22 UTC** — New index populated; Workers updated to point to new index name via KV config flag.
- **15:23 UTC** — Semantic search results return to normal; `semantic_search_results_p50` returns to baseline.

## Root Cause

The migration script assumed that dimension mismatch would be surfaced as an API error. The Vectorize upsert API returns `{ count: N }` in the success response, but the script did not validate that `count` matched the number of vectors submitted in each batch—it only checked for HTTP 200:

```typescript
// scripts/migrate-vectors.ts — pre-fix (the bug)

async function upsertBatch(
  vectors: VectorizeVector[],
  env: Env,
): Promise<void> {
  // Vectors are 1024-dimensional; index is 768-dimensional
  const result = await env.VECTORIZE_INDEX.upsert(vectors);

  // BUG: only checks for thrown error; does not validate result.count
  // Vectorize returns { count: 0 } silently when dimensions don't match
  console.log(`Upserted batch: ${JSON.stringify(result)}`);
  // Output: { "count": 0 } — silent discard, no exception
}
```

Additionally, the index was emptied before the new vectors were confirmed as successfully inserted. This is a classic delete-before-insert anti-pattern that left the index in an empty state for the 75-minute window between deletion and successful re-population with the correctly dimensioned index.

```typescript
// Migration script execution order — pre-fix
await deleteAllVectors(env.VECTORIZE_INDEX);    // Step 1: destructive, irreversible
await upsertNewVectors(env.VECTORIZE_INDEX);    // Step 2: silently fails due to dimension mismatch
// Result: index is empty, zero vectors stored
```

## Fix Applied

**Immediate fix** (14:47 UTC): create a correctly dimensioned index and re-populate it while keeping the empty old index in place (not deleting it until the new one is verified):

```bash
# Create new index with correct dimensions
wrangler vectorize create semantic-search-v2 \
  --dimensions=1024 \
  --metric=cosine
```

```typescript
// scripts/migrate-vectors-v2.ts — fixed migration script

const EXPECTED_DIMENSIONS = 1024;

async function upsertBatchSafe(
  vectors: VectorizeVector[],
  index: VectorizeIndex,
): Promise<number> {
  // Pre-flight: validate all vectors have correct dimensions
  for (const v of vectors) {
    if (v.values.length !== EXPECTED_DIMENSIONS) {
      throw new Error(
        `Dimension mismatch: expected ${EXPECTED_DIMENSIONS}, got ${v.values.length} for id=${v.id}`
      );
    }
  }

  const result = await index.upsert(vectors);

  // Post-flight: validate that upserted count matches submitted count
  if (result.count !== vectors.length) {
    throw new Error(
      `Upsert count mismatch: submitted=${vectors.length} accepted=${result.count}. ` +
      `Possible dimension mismatch or index schema error.`
    );
  }

  return result.count;
}

// Migration order: populate new index first, then switch traffic, then clean up old
async function runMigration(env: Env) {
  console.log('Step 1: populating new index (old index still serves traffic)');
  await populateNewIndex(env.VECTORIZE_INDEX_V2);

  console.log('Step 2: verifying new index count');
  const { vectorCount } = await env.VECTORIZE_INDEX_V2.describe();
  if (vectorCount < MIN_EXPECTED_VECTORS) {
    throw new Error(`New index has only ${vectorCount} vectors; aborting cutover`);
  }

  console.log('Step 3: switching traffic to new index via KV flag');
  await env.KV_CONFIG.put('vectorize_index_name', 'semantic-search-v2');

  console.log('Step 4: waiting 10 minutes before deleting old index');
  // Handled by a deferred cleanup job, not inline
}
```

**Worker update** to read the active index name from KV config:

```typescript
// search-worker/src/vectorize.ts — post-fix

export async function querySimilar(
  embedding: number[],
  env: Env,
): Promise<VectorizeMatch[]> {
  // Index name resolved from KV; allows zero-downtime index swaps
  const indexName = await env.KV_CONFIG.get('vectorize_index_name') ?? 'semantic-search-v2';
  const index = env[indexName as keyof Env] as VectorizeIndex;

  const { matches } = await index.query(embedding, { topK: 20, returnMetadata: true });

  if (matches.length === 0) {
    // Emit a metric rather than silently returning empty — catches future mismatches
    env.ANALYTICS.writeDataPoint({
      indexes: ['vectorize_empty_result'],
      doubles: [embedding.length],
      blobs: [indexName],
    });
  }

  return matches;
}
```

## What We Learned

1. **Vectorize index dimensions are immutable at creation time.** There is no `ALTER INDEX` equivalent; a dimension change always requires creating a new index, re-ingesting all vectors, and switching traffic.
2. **Vectorize does not throw on dimension mismatch during upsert**—it silently discards or truncates the vectors and returns `{ count: 0 }`. Always validate `result.count === batch.length` after every upsert.
3. **Delete-before-insert migrations for search indexes cause user-visible outages.** The correct pattern is populate-then-switch: build the new index in parallel, verify it, then atomically redirect traffic via a feature flag.
4. **Empty result sets are not always surfaced as errors.** Monitoring must track result count distribution (p50, p99), not just HTTP error rates, to detect silent degradation.
5. **Model upgrades that change embedding dimensions are a breaking schema change** and must trigger an index recreation workflow, just as a database schema migration triggers a migration script.

## Prevention

- **Pre-flight dimension assertion**: add a startup check in any Worker or script that upserts to Vectorize to call `index.describe()` and assert that `config.dimensions` matches the embedding model's output size.

```typescript
async function assertIndexDimensions(
  index: VectorizeIndex,
  expectedDimensions: number,
): Promise<void> {
  const { config } = await index.describe();
  if (config.dimensions !== expectedDimensions) {
    throw new Error(
      `Index dimension mismatch: index has ${config.dimensions}, model produces ${expectedDimensions}. ` +
      `Create a new index with the correct dimensions.`
    );
  }
}
```

- **Upsert count validation**: wrap all `index.upsert()` calls in a helper that throws if `result.count !== batch.length`.
- **Alerting on zero-result queries**: emit a metric when a Vectorize query returns zero matches and alert when the rate of zero-result queries exceeds 5% of total queries.
- **Blue-green index migration runbook**: document and enforce the populate-then-switch pattern for all Vectorize index changes; block the delete-old-index step behind a manual gate.
- **Index schema in version control**: store the Vectorize index creation command (`wrangler vectorize create ...`) in an `infra/vectorize.sh` script in the repo so the dimensions value is code-reviewed before any re-creation.

## Anti-patterns

- Creating a Vectorize index and assuming its dimensions can be changed later.
- Deleting all vectors from an index before confirming the replacement vectors have been successfully inserted.
- Treating a 200 OK from `index.upsert()` as proof that vectors were accepted without checking `result.count`.
- Monitoring only HTTP error rates on search endpoints; a silent dimension mismatch shows HTTP 200 with zero results.
- Embedding model upgrades handled by a single team without notifying all teams that write to or query the same Vectorize index.

## Gotchas

- `index.describe()` returns `vectorCount` which reflects vectors currently stored—calling it before migration confirms the baseline, and calling it after upsert confirms success or detects silent discard.
- The `metric` parameter (cosine, euclidean, dot-product) is also immutable at index creation; a metric change also requires a new index.
- Vectorize `query()` can return zero matches legitimately for novel queries—use a known-good test vector in monitoring smoke tests to distinguish "no relevant content" from "index is broken."
- Cloudflare Vectorize has a rate limit on upsert operations; re-ingesting millions of vectors in a single migration requires batch sizing and exponential backoff, otherwise upsert batches may be dropped silently alongside dimension-mismatch drops.
- The `namespace` filter in Vectorize queries must match the namespace set during upsert; if old vectors used the default namespace and new vectors use an explicit namespace, queries filtering by namespace will also return empty results.

## Verification

1. Call `env.VECTORIZE_INDEX_V2.describe()` after migration and confirm `vectorCount` equals the expected number of indexed items.
2. Run the semantic search smoke test suite against the new index; confirm p50 result count returns to historical baseline (≥6 matches per query for common queries).
3. Monitor Analytics Engine `vectorize_empty_result` event count for 24 hours post-migration; confirm it returns to pre-incident baseline.
4. Verify the old index is deleted only after 24 hours of confirmed normal operation on the new index.

## Related

- [Workers AI Cold Start Latency Production Lesson](workers-ai-cold-start-latency-production-lesson.md)
- [Workers AI Model Deprecation Migration ADR](workers-ai-model-deprecation-migration-adr.md)
- [D1 Migration Rollback Failed Production Lesson](d1-migration-rollback-failed-production-lesson.md)
- [R2 Eventual Consistency Cache Invalidation Incident](r2-eventual-consistency-cache-invalidation-incident.md)

## Sources

- https://developers.cloudflare.com/vectorize/reference/client-api/
- https://developers.cloudflare.com/vectorize/best-practices/
- https://developers.cloudflare.com/vectorize/changelog/
