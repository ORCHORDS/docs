# Vectorize Pre-Filter vs Post-Filter ANN Search with Metadata

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You have a Vectorize index with metadata fields (e.g., `tenant_id`, `document_type`, `publish_date`, `language`) and need to run filtered semantic search — return only vectors that match both a similarity criterion and a metadata predicate. Two approaches exist with fundamentally different recall characteristics: pre-filtering (restrict the ANN candidate set before similarity scoring) and post-filtering (score the full index, then apply metadata predicates). Choosing the wrong approach leads to either poor recall (too few results) or full-table scans (too slow).

This article maps Vectorize's filtering capabilities to the two strategies, shows when each applies, and provides patterns for working around Vectorize's current limitations when strict pre-filtering causes empty result sets.

## Context

Cloudflare Vectorize supports metadata filtering via the `filter` parameter on `query()` calls. Under the hood, Vectorize applies metadata filtering as a pre-filter in its ANN index: it restricts the candidate set to vectors that match the filter before running the approximate nearest-neighbour search. This is fast for high-cardinality filters (e.g., `tenant_id = "acme"`) but can degrade recall severely for selective filters that match a small fraction of the index, because ANN algorithms need a minimum candidate pool to operate accurately.

Post-filtering — running ANN over the full index and then discarding non-matching results — is not directly exposed by Vectorize, but can be approximated by requesting a large `topK` and filtering the returned matches in Worker code. This trades index traversal cost for deterministic recall.

## Understanding Vectorize's Metadata Filter Behaviour

Vectorize accepts a `filter` object in the `VectorizeQueryOptions.filter` field. The filter is expressed as simple equality or range predicates on metadata fields:

```typescript
// Vectorize filter expression examples
const exactMatchFilter = { tenant_id: { $eq: "acme" } };
const rangeFilter      = { publish_epoch: { $gt: 1700000000, $lt: 1800000000 } };
const multiFieldFilter = { tenant_id: { $eq: "acme" }, language: { $eq: "en" } };
// No OR predicates or nested conditions in current Vectorize API
```

These filters are applied before the ANN graph traversal. Vectors not matching the filter are excluded from the HNSW candidate graph walk, which means:

- Very selective filters (matching <1% of the index) effectively run similarity search on a tiny subgraph, degrading recall
- Broad filters (matching >10% of the index) behave close to full-index search with a cheap pre-check

## Pre-Filter Strategy: When to Use It

Use Vectorize's built-in pre-filter when:

1. The filter predicate matches a substantial fraction of the index (>5%)
2. You are enforcing tenant isolation — every query MUST be scoped to a single tenant, and returning results from other tenants is a correctness violation, not just a quality issue #<number>. The filtered subset is large enough that ANN recall remains acceptable (>500 matching vectors recommended)

```typescript
// worker.ts — pre-filter path (Vectorize native)
export async function searchWithPreFilter(
  query: string,
  tenantId: string,
  env: Env,
  topK = 10
): Promise<VectorizeMatches> {
  const { data } = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [query],
  });

  return env.VECTORIZE.query(data[0], {
    topK,
    returnMetadata: "all",
    filter: {
      tenant_id: { $eq: tenantId },
    },
  });
}
```

For tenant isolation this is the correct and only safe approach — never rely on post-filtering for security boundaries because post-filtering can return results before the filter is applied if an implementation error occurs.

## Post-Filter Strategy: Approximation via Oversized topK

When the filter is highly selective (e.g., `category = "archived" AND year = 2019`), Vectorize's pre-filter will produce poor recall because only a handful of vectors match. Instead, request a large topK (e.g., 200) and filter in Worker memory:

```typescript
// post-filter-search.ts
interface FilteredMatch {
  id: string;
  score: number;
  metadata: Record<string, string | number | boolean>;
}

export async function searchWithPostFilter(
  query: string,
  metadataPredicate: (metadata: Record<string, string | number | boolean>) => boolean,
  env: Env,
  targetResults = 10,
  oversampleFactor = 20 // request topK = targetResults * oversampleFactor
): Promise<FilteredMatch[]> {
  const { data } = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [query],
  });

  // Retrieve a large candidate pool without metadata filter
  const candidates = await env.VECTORIZE.query(data[0], {
    topK: Math.min(targetResults * oversampleFactor, 1000), // Vectorize topK cap
    returnMetadata: "all",
  });

  // Apply predicate in Worker memory
  const filtered = candidates.matches
    .filter((m) => m.metadata && metadataPredicate(m.metadata as Record<string, string | number | boolean>))
    .slice(0, targetResults);

  return filtered.map((m) => ({
    id: m.id,
    score: m.score,
    metadata: m.metadata as Record<string, string | number | boolean>,
  }));
}

// Usage: filter to English archived documents from 2019
const results = await searchWithPostFilter(
  "machine learning techniques",
  (meta) =>
    meta.language === "en" &&
    meta.status === "archived" &&
    Number(meta.year) === 2019,
  env,
  10,
  20
);
```

The post-filter approach assumes that the top-200 ANN results contain at least 10 matching documents. If the matching fraction is 5% and the index has 100,000 vectors, only ~5,000 match — within a topK=200 candidate pool the recall is reasonable if the 10 most relevant are in the top-200 by similarity.

## Hybrid Strategy: Pre-Filter on High-Cardinality, Post-Filter on Low-Cardinality

Combine both strategies by pre-filtering on a high-cardinality field (good recall) and post-filtering on a low-cardinality field (too selective for pre-filter):

```typescript
// hybrid-filter-search.ts
export async function hybridFilteredSearch(
  query: string,
  tenantId: string, // high cardinality: thousands of vectors per tenant
  additionalFilter: (meta: Record<string, unknown>) => boolean, // low cardinality
  env: Env,
  targetResults = 10
): Promise<FilteredMatch[]> {
  const { data } = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [query],
  });

  // Pre-filter on tenant_id (guaranteed correctness + large matching set)
  // Request more than needed to survive post-filtering
  const candidates = await env.VECTORIZE.query(data[0], {
    topK: targetResults * 10,
    returnMetadata: "all",
    filter: { tenant_id: { $eq: tenantId } },
  });

  // Post-filter on additional low-cardinality predicates
  return candidates.matches
    .filter(
      (m) =>
        m.metadata &&
        additionalFilter(m.metadata as Record<string, unknown>)
    )
    .slice(0, targetResults)
    .map((m) => ({
      id: m.id,
      score: m.score,
      metadata: m.metadata as Record<string, string | number | boolean>,
    }));
}
```

## Namespace as a Pre-Filter Alternative

Vectorize namespaces provide an alternative partitioning mechanism: vectors in different namespaces are completely isolated and queried independently. For tenant isolation where each tenant has enough vectors to maintain good ANN recall, namespace-per-tenant is more reliable than metadata pre-filtering:

```typescript
// namespace-search.ts
export async function searchInNamespace(
  query: string,
  tenantNamespace: string,
  env: Env,
  topK = 10
): Promise<VectorizeMatches> {
  const { data } = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [query],
  });

  return env.VECTORIZE.query(data[0], {
    topK,
    namespace: tenantNamespace, // query restricted to this namespace entirely
    returnMetadata: "all",
  });
}

// Ingest with namespace
async function ingestToNamespace(
  doc: { id: string; text: string; metadata: Record<string, string> },
  tenantNamespace: string,
  env: Env
): Promise<void> {
  const { data } = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [doc.text],
  });

  await env.VECTORIZE.upsert([
    {
      id: doc.id,
      values: data[0],
      metadata: doc.metadata,
      namespace: tenantNamespace,
    },
  ]);
}
```

Namespace queries bypass metadata pre-filtering entirely and operate on a dedicated sub-index, giving deterministic isolation without the recall degradation of selective metadata filters.

## Measuring Filter Selectivity

Before choosing a strategy, measure how selective your filter is:

```typescript
// selectivity-probe.ts
export async function measureFilterSelectivity(
  filter: VectorizeVectorMetadataFilter,
  env: Env,
  probeVectors = 5
): Promise<{ avgFilteredCount: number; totalVectors: number }> {
  // Generate random probe vectors and compare filtered vs unfiltered topK
  const results: number[] = [];
  const PROBE_K = 500;

  for (let i = 0; i < probeVectors; i++) {
    const probeVec = Array.from({ length: 768 }, () => Math.random() * 2 - 1);
    const mag = Math.sqrt(probeVec.reduce((s, v) => s + v * v, 0));
    const unitProbe = probeVec.map((v) => v / mag);

    const filtered = await env.VECTORIZE.query(unitProbe, {
      topK: PROBE_K,
      filter,
      returnMetadata: "none",
    });

    results.push(filtered.matches.length);
  }

  const avgFilteredCount = results.reduce((s, v) => s + v, 0) / results.length;
  return { avgFilteredCount, totalVectors: -1 }; // Vectorize doesn't expose total count
}

// Decision rule
function chooseFilterStrategy(avgFilteredCount: number): "pre-filter" | "post-filter" | "hybrid" {
  if (avgFilteredCount < 50) return "post-filter"; // too few candidates for ANN
  if (avgFilteredCount < 200) return "hybrid"; // borderline — pre-filter on broad, post-filter on narrow
  return "pre-filter"; // sufficient candidates for good ANN recall
}
```

## Anti-patterns

- Using pre-filter with highly selective predicates (matching <50 vectors) and wondering why results are irrelevant or empty — the ANN graph has too few candidates to find good neighbours
- Using post-filter for tenant isolation — post-filtering is applied in Worker code after Vectorize returns results; a code bug could leak cross-tenant data
- Setting `topK=10` with post-filtering and expecting consistent 10 results — if only 3 of the top-10 ANN results match the predicate, you get 3 results, not 10; over-sample
- Applying multiple range predicates simultaneously — Vectorize supports limited compound filter expressions; complex predicates may require post-filtering
- Using namespace isolation AND metadata pre-filter simultaneously for the same dimension — redundant and does not improve recall
- Not logging how many results survived post-filtering — opaque post-filters make it impossible to distinguish "no relevant documents" from "filter too restrictive"

## Gotchas

- Vectorize `topK` has an upper bound (consult current documentation — typically 100 or 1000). If your post-filter strategy requires more candidates than the limit, you must adjust the filter strategy.
- Metadata values stored in Vectorize are strings by default. Numeric range comparisons (`$gt`, `$lt`) require that the metadata was stored as a number type, not a string. `"2019"` (string) will not satisfy `{ year: { $gt: 2018 } }` where year was stored as a string.
- Namespace-per-tenant imposes its own limits. If a tenant has fewer than ~100 vectors, ANN quality degrades regardless of namespace isolation — minimum viable namespace size is around 500 vectors.
- Post-filtering in a Worker is synchronous JavaScript and runs against the topK returned matches. For very large topK (>500), iterating matches adds measurable CPU time within the Worker CPU limit (50ms default, 30s with Unbound Workers).
- `filter` and `namespace` can be combined — a namespace query with a metadata filter applies pre-filtering within the namespace.

## Verification

```typescript
// Verify filter strategy recall with a labelled golden set
async function testFilteredRecall(env: Env): Promise<void> {
  const KNOWN_ID = "doc-test-001"; // a vector known to be in the index with specific metadata

  // Pre-filter recall
  const preFiltered = await env.VECTORIZE.query(
    (await env.AI.run("@cf/baai/bge-base-en-v1.5", { text: ["test document content"] })).data[0],
    { topK: 10, filter: { doc_type: { $eq: "test" } }, returnMetadata: "all" }
  );
  const foundViaPreFilter = preFiltered.matches.some((m) => m.id === KNOWN_ID);

  // Post-filter recall (oversample topK)
  const postFiltered = await (async () => {
    const all = await env.VECTORIZE.query(
      (await env.AI.run("@cf/baai/bge-base-en-v1.5", { text: ["test document content"] })).data[0],
      { topK: 200, returnMetadata: "all" }
    );
    return all.matches.filter((m) => (m.metadata as any)?.doc_type === "test");
  })();
  const foundViaPostFilter = postFiltered.some((m) => m.id === KNOWN_ID);

  console.log(`Pre-filter recall for known ID: ${foundViaPreFilter}`);
  console.log(`Post-filter recall for known ID: ${foundViaPostFilter}`);
  console.log(`Pre-filter result count: ${preFiltered.matches.length}`);
  console.log(`Post-filter result count: ${postFiltered.length}`);
}
```

## Related

- `vectorize-metadata-filtering-complex-predicates.md` — advanced Vectorize filter expressions
- `vectorize-multi-tenant-namespace-partitioning.md` — namespace-per-tenant architecture
- `vectorize-dot-product-vs-cosine-similarity.md` — metric selection for ANN search
- `rag-hybrid-search.md` — combining BM25 keyword search with vector search for improved recall

## Sources

- Cloudflare Vectorize metadata filtering docs: https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
- Cloudflare Vectorize namespaces: https://developers.cloudflare.com/vectorize/reference/
- Malkov, Y. & Yashunin, D. "Efficient and Robust ANN Search using HNSW." IEEE TPAMI, 2018 — pre-filter impact on HNSW recall
