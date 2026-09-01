# LLM Embedding Cache and Vector Reuse

Embeddings are the quiet majority of many AI system costs. Every document chunk, query, and cached passage passes through an embedding model before retrieval, and unlike generation, embedding the same text twice produces identical vectors — a property that makes caching uniquely effective. Yet embedded systems routinely re-embed the same content on every ingestion run, re-embed unchanged documents after pipeline changes, and pay vector-store write costs for vectors that already exist. Embedding reuse is straightforward engineering with outsized returns and a small set of rules that make it safe.

## Scope

This article covers embedding caching and vector reuse in RAG and search systems: content-hash keying, invalidation policy, namespacing by model version, and the consistency controls that prevent stale or mismatched vectors from poisoning retrieval. It applies to teams operating embedding pipelines feeding vector stores.

Excluded: embedding model selection and training, quantization of stored vectors (a storage decision), and vector-store indexing mechanics (ANN index parameters), which interact with reuse but are separate concerns.

The property everything rests on: embeddings are deterministic functions of (model, model version, input text, and in some cases instruction prefixes). Same inputs, same vector — which means reuse is safe if and only if all determinants match. Every control below is an enforcement of that condition.

## Workflow or implementation guidance

1. **Key the cache on the true determinants.** The cache key is a hash over: model identifier, model version/revision, exact input text, and any instruction or prefix the API applies (query-versus-document prompts in some models differ). Hashing only the text is the classic defect: a model upgrade then serves old vectors under a new name. Compute the key at a single choke point in the codebase so no path can bypass it.
2. **Namespace vector-store collections by model version.** Rather than deleting and rewriting on model change, write to a new collection (or namespace) and cut over atomically after validation. This keeps rollback possible: the previous collection still exists and switching back is a pointer change, not a re-embedding marathon.
3. **Make ingestion idempotent.** Re-running ingestion over the same corpus must be a no-op for unchanged documents: source content hash matches, embedding-model tuple matches, therefore skip. Track content hashes at the document level so a rerun after partial failure resumes rather than restarts. Idempotent ingestion is what makes pipeline re-runs cheap enough to run frequently.
4. **Handle near-duplicate content explicitly.** Identical chunks appear across documents (boilerplate, headers, licenses). A chunk-level content-hash registry deduplicates embedding calls across documents automatically once the cache is keyed properly — measure the hit rate; corpora with heavy boilerplate see large savings here.
5. **Decide query-embedding caching on its own terms.** Query embeddings are as cacheable as document embeddings, but query distributions are long-tailed: most queries occur once. A bounded query cache with small TTL catches head queries and popular retrieval corpora while the tail pays full price. Size it from query-frequency statistics, not document-corpus statistics.
6. **Plan the model-upgrade migration as a first-class task.** Model upgrades re-embed the world. Budget the cost, run the new collection in shadow (compare retrieval quality on the evaluation set), cutover atomically, keep the old collection for a defined rollback window, then reclaim storage. Skipping the shadow comparison is how silent retrieval regressions ship.

## Controls

- **Determinant-complete cache keys.** A single shared implementation of key computation; unit tests assert that changing any determinant (model, version, text, instruction) changes the key.
- **Collection/version registry.** The mapping from logical collection name to physical versioned collection is recorded and deployed as configuration; nothing references physical names directly.
- **Ingestion idempotency check.** A dry-run mode reports would-embed counts before executing; a second consecutive run reports near zero — this is run in CI on a fixture corpus.
- **Hit-rate and cost telemetry.** Cache hit ratio, embedding API spend, and vector-store write volume trended; a sudden hit-rate drop signals a determinant change nobody announced.
- **Shadow-comparison gate.** New embedding versions promote only after retrieval-quality comparison on the golden query set meets or beats the incumbent within tolerance.

## Validation evidence

- Idempotency evidence: two consecutive ingestion runs over the fixture corpus, the second embedding ~0 new chunks, recorded in CI.
- Migration evidence: for each model-version cutover, the shadow retrieval-quality comparison, cutover timestamp, rollback-window definition, and eventual old-collection removal date.
- Cache economics: measured hit rates and embedding spend before/after enabling the cache on production traffic, with the determinant tuple version recorded.
- Retrieval regression suite results tied to the physical collection version in use, so quality numbers are always attributable to a specific embedding configuration.

## Failure modes and correction

- **Stale-vectors-after-upgrade.** Vectors from the old model served under the new configuration because the cache key ignored model version. Correction: determinant-complete keys (this defect is the reason the control exists); audit the vector store for key-prefix anomalies; re-embed affected content.
- **Instruction-tuple mismatch.** Query embeddings produced with a query instruction are compared against document embeddings produced without one (or vice versa); retrieval quality degrades subtly. Correction: encode the instruction in the key and assert symmetric configuration at retrieval time; the shadow-comparison gate catches the regression before cutover.
- **Unbounded growth of orphaned collections.** Old namespaces accumulate after migrations "temporarily" retained; storage cost climbs and operators lose track of which collection is live. Correction: registry with enforced retention policy — rollback windows have expiry dates and deletion is automated.
- **Cache stampede on cold start or expiry.** A pipeline restart re-embends the hot corpus simultaneously, spiking provider rate limits and cost. Correction: single-flight locking around key computation and warming schedules; the cache treats concurrent identical keys as one embedding call.
- **Query-cache poisoning via normalization drift.** Text normalization changes (whitespace, unicode forms) silently change keys, halving hit rates across a deploy. Correction: normalization is part of the documented key definition; normalization changes bump the key version deliberately.

## Limitations

Determinism assumptions hold for standard embedding models but providers may change hosted model implementations under stable names; pinning versions where the API allows and monitoring for drift (same input, shifted vector) bounds the exposure. Near-neighbor duplicate detection (embedding-based dedupe of semantically similar text) is a different technique with different costs and is not covered here. Vector-store capabilities for aliases and namespace switching vary by product; migration mechanics depend on the store's current documentation. This article assumes offline/document embeddings dominate; systems dominated by novel query traffic see much smaller wins.

## Canonical sources

- Pinecone documentation, Managing Indexes: https://docs.pinecone.io/guides/indexes
- Hugging Face Sentence-Transformers documentation, Semantic Search: https://sbert.net/examples/applications/semantic-search/README.html
