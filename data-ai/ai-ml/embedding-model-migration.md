# embedding-model-migration

**Issue:** Switching the embedding model breaks retrieval because existing
vectors were produced by a different model and are not comparable to new
vectors, causing recall to collapse.
**Date:** 2026-08-13
**Status:** documented

## Symptom

You upgraded from `text-embedding-ada-002` (1536 dim) to
`text-embedding-3-large` (3072 dim), or swapped from OpenAI to a Cohere or
open-source model. Immediately:
- **Retrieval quality plummets.** Top-k results are irrelevant or the store
  returns zero useful matches, even for queries that worked before.
- **Newly ingested documents outperform old ones** for queries they should
  not, because new vectors are only comparable to other new vectors.
- **Cosine similarity scores look sane** (0.7-0.9) but ranking is garbage,
  because the score is meaningful only within one model's space.
- **The migration "looked complete"** (index rebuilt, code updated) but search
  still serves stale vectors from a cache, a replica, or a second collection.
- **Dimension mismatch crashes** appear intermittently — a queue worker or
  background ingestion job is still calling the old model.

The root cause is that vectors are model-specific. Mixing vectors from two
different embedding models in one index produces nonsense results even though
no error is raised.

## Pattern / Solution

### Principle: never mix models in one index

Every vector in a collection must come from the same model, the same version,
and the same dimensionality. The migration must be atomic: all old vectors
replaced, or a clean dual-collection cutover.

### Strategy 1: Re-embed everything (small / medium corpora)

For corpora under a few million chunks, the simplest path is to re-embed from
source and swap the index.

```python
import openai

NEW_MODEL = "text-embedding-3-large"

def reembed_all(documents, batch_size=2048):
    new_vectors = {}
    for batch in chunked(documents, batch_size):
        texts = [doc.text for doc in batch]
        resp = openai.embeddings.create(model=NEW_MODEL, input=texts)
        for doc, item in zip(batch, resp.data):
            new_vectors[doc.id] = item.embedding
    return new_vectors

# 1. Re-embed into a NEW collection (do not touch the live one)
new_store.create_index(dim=3072, metric="cosine")
for doc_id, vector in reembed_all(all_docs):
    new_store.upsert(doc_id, vector, metadata=docs[doc_id].metadata)

# 2. Validate recall on a held-out eval set against the new store
recall_new = evaluate_recall(eval_set, new_store)
assert recall_new >= recall_old * 0.95  # allow small dip, catch disasters

# 3. Atomic cutover: swap the collection pointer
config.set("vector_collection", "v2_large")
```

### Strategy 2: Dual-collection with traffic split (large corpora)

For very large corpora where re-embedding takes hours or days, run both
collections in parallel and shift traffic gradually.

```python
class DualEmbeddingStore:
    def __init__(self, old_store, new_store, shadow_pct=0.0):
        self.old = old_store
        self.new = new_store
        self.shadow_pct = shadow_pct  # fraction of queries hitting new store

    def search(self, query_text, top_k=10):
        # Embed query with BOTH models (costs 2x embedding calls during migration)
        old_q = embed_old(query_text)
        results_old = self.old.search(old_q, top_k=top_k)

        if random.random() < self.shadow_pct:
            new_q = embed_new(query_text)
            results_new = self.new.search(new_q, top_k=top_k)
            log_comparison(query_text, results_old, results_new)
            return results_new  # or return old if new is worse
        return results_old
```

Raise `shadow_pct` from 0.05 to 0.5 to 1.0 over days, watching eval metrics,
then cut over.

### Strategy 3: Dimension reduction / extension

OpenAI's text-embedding-3 family supports shortening via Matryoshka
representation — you can request 1536 or 256 dims from a 3072-dim model.

```python
# Use a smaller dim to save storage while keeping the new model
resp = openai.embeddings.create(
    model="text-embedding-3-large",
    input=texts,
    dimensions=1536,  # truncate from 3072
)
# WARNING: once you pick a dimension, you cannot mix it with full-dim vectors
```

### Migration checklist

1. Freeze ingestion during cutover, or queue new docs for post-migration
   re-embedding.
2. Re-embed from the source text, not from cached chunks — chunking logic may
   have changed.
3. Update the model name and dimension in config, not just in one call site.
4. Flush all semantic caches — cached query results from the old embedding
   space are invalid.
5. Update the eval harness to use the new model for query embeddings.
6. Tag every vector with `embedding_model` and `embedding_version` metadata so
   future migrations can detect mixed-model indices.

```python
# Self-check: detect a mixed-model index before it causes silent recall loss
def assert_uniform_model(store):
    models = set()
    for meta in store.scan_metadata(limit=10000):
        models.add(meta.get("embedding_model"))
    assert len(models) == 1, f"MIXED INDEX: {models}"
```

## Gotchas

- **Dimension mismatch is the easy failure.** The silent failure is when two
  models have the same dimension (e.g., both 1536) but different vector
  spaces — cosine similarity returns plausible-looking numbers that are
  meaningless. Always store the model name in metadata and assert uniformity.
- **Re-embedding cost can be large.** Re-embedding 10M chunks on a premium
  API can cost hundreds of dollars. Batch aggressively and consider a cheaper
  or self-hosted model for the initial bulk pass.
- **Semantic caches poison retrieval after migration.** If your cache stores
  old-model query embeddings, a cache hit returns stale or incomparable
  results. Purge the cache or version it by embedding model.
- **Background jobs are the usual culprit for mixed indices.** A cron worker,
  a queue consumer, or a lambda that was not redeployed keeps writing
  old-model vectors into the new collection. Search every code path that
  writes to the store.
- **Evaluation against old recall is mandatory.** A new model can have worse
  recall on your specific domain even if it scores higher on MTEB. Always
  run your own eval set, not public benchmarks.
- **Rerankers may need retraining.** If you trained a cross-encoder on
  old-model embeddings or old-chunk boundaries, it may degrade after the
  migration even if the embeddings improved.
- **Rollback plan.** Keep the old collection for at least 2 weeks after
  cutover. If metrics drop, flip the pointer back. Do not delete it on day 1.
- **Query embeddings must match.** The most common bug is re-embedding all
  documents but forgetting to update the query-side embedding call, so
  queries are embedded with the old model against the new index.

## Related
- `vector-embeddings-model-selection.md` — choosing the model in the first place
- `embedding-batching.md` — efficient bulk re-embedding during migration
- `rag-embedding-models.md` — model-specific RAG concerns
- `rag-evaluation-ragas.md` — measuring recall before and after migration
- `semantic-caching-patterns.md` — caches must be versioned by embedding model
- `model-versioning-strategy.md` — versioning the embedding model in metadata
