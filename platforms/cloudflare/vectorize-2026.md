# cloudflare-vectorize-2026

- **Issue**: Vectorize grew up: 5M-dim indexes (up from 200K), metadata filtering with `$in`/`$nin`/range operators, and an explicit `returnMetadata` mode that lets you skip returning vector values. The old patterns from 2024 docs are now incomplete.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; supplements `documentation/categories/cloudflare/vectorize-best-practices.md` (which covers the 2024 surface).

## Symptom

- You build a RAG pipeline on Vectorize and your topK query is slow because it always returns full vector values you don't need.
- You want to filter by metadata (customer, tenant, category) and the 2024-era `$eq`/`$ne` only is not enough.
- Your index is approaching the 200,000-dimension limit and you need a bigger bucket.
- Your namespace filter works but you also want to filter on a non-namespace property and the docs say "create a metadata index" without telling you when or how many.

## Root cause (and the 2026 numbers)

### Index size

- **Per-index limit is now 5,000,000 vector dimensions**, up from 200,000. The dimension count is `num_vectors × dim` (e.g., 50,000 vectors at 1024-d = 51.2M dims, over the limit). Plan capacity per index accordingly.
- Metadata filtering now requires an explicit metadata index created before vectors are inserted. Old indexes (before 2023-12-06) cannot be migrated.

### Metadata indexes

- **Up to 10 metadata indexes per Vectorize index**.
- Supported types: `string`, `number`, `boolean`.
- Up to **10 KiB of metadata per vector**.
- For `string` indexes, only the **first 64 bytes (UTF-8 well-formed boundary)** are indexed. Anything past 64 bytes is stored but not filterable.
- For `number` indexes, precision is `float64`.
- Filter object compact JSON must be **< 2048 bytes**; keys cannot be empty, contain `.` (reserved for nesting), start with `$`, or be longer than 512 characters.
- Allowed operators: `$eq`, `$ne`, `$in`, `$nin`, `$lt`, `$lte`, `$gt`, `$gte`. **Only upper-bound range and lower-bound range can be combined** within the same filter — no `$lt` + `$lt`.

### Return shape

- `returnVectors` is **deprecated**. Use `returnMetadata` and `returnValues` (both default `false`).
- `returnMetadata: "all"` fetches all metadata per vector; `topK` is limited to **50** in that mode.
- `returnMetadata: "indexed"` fetches only indexed-field metadata; no latency overhead, but long text fields may be truncated to 64 bytes.
- `returnValues: true` returns the full vector array. Skip it when you only need the metadata + the score.

### Namespaces

- Namespace filtering is on by default. Use `namespace` on both `insert` and `query` to scope.
- Use namespaces to enforce tenant isolation, not custom metadata fields. It is faster, and there is no 10-index limit.

## Patterns

### Per-tenant isolation

```ts
// Insert: scope by namespace
await env.VECTORIZE.insert([{
  id: `${tenantId}:${docId}`,
  values: embedding,
  metadata: { url, title, chunk_index },
  namespace: tenantId,
}], { namespace: tenantId })

// Query: enforce the tenant at the namespace level
const results = await env.VECTORIZE.query(queryVector, {
  topK: 10,
  namespace: tenantId,
  returnMetadata: "indexed",
  returnValues: false,
})
```

### Filter on a category metadata

```sh
# Create the metadata index once (CLI, on a new index)
npx wrangler vectorize create-metadata-index prod-index --property-name=category --type=string
npx wrangler create-metadata-index prod-index --property-name=timestamp --type=number
```

```ts
// Query: combine namespace + metadata filter
const results = await env.VECTORIZE.query(queryVector, {
  topK: 10,
  namespace: "tenant-a",
  filter: { category: { $in: ["docs", "kb"] }, timestamp: { $gte: 1700000000 } },
  returnMetadata: "indexed",
})
```

### Skip vectors on read

```ts
const { matches } = await env.VECTORIZE.query(queryVector, {
  topK: 20,
  returnMetadata: "all",   // up to 50; get full metadata, no values
  returnValues: false,
})
```

## Verification

- **Hit-rate** on a tenant filter: log `namespace` on every query; verify the namespace is present and matches the auth context. A missing namespace is a tenant-leak risk.
- **Filter plan cost**: $in with 1000 values still works but adds latency. Cap $in arrays at ~50.
- **Size check**: every quarter, compute `total_vectors × dim` for each index. If you're over 80% of 5M dims, split.
- **Latency p95** for `returnMetadata: "all"` queries should be < 300 ms; if not, your index is too dense or your filter is non-selective.

## Gotchas

- **Index the filter, then insert.** You cannot add a metadata index to an existing index that didn't have one. The old data is unfilterable. Plan ahead.
- **`returnMetadata: "all"` caps `topK` at 50.** If you need more, drop to `"indexed"` and accept the truncation.
- **64-byte string limit is hard.** URLs, IDs, slugs fit; titles and bodies don't. For filterable text, use a separate `slug` or `category` field.
- **Filter is applied first**, then `topK` taken from the filtered set. A highly selective filter can drop you below `topK` results with no error.
- **Compact JSON for filter must be < 2048 bytes** — a 1000-element `$in` array of 50-char strings blows this. Use enum-style filters for high-cardinality cases.
- **Combined range filters are upper-or-lower only**, not both. Use two filters or restructure.
- **5M-dim limit is per index, not per account.** A 1M-vector, 1024-d index is already over. Plan to split.
- **The 2023-12-06 cutoff is forever** — those old indexes do not get metadata filtering retrofitted.

## Related

- `documentation/categories/cloudflare/vectorize-best-practices.md` — pre-2026 patterns
- `documentation/categories/cloudflare/ai-search-2026.md` — the managed retrieval layer built on top of Vectorize
- `documentation/categories/cloudflare/ai-gateway-best-practices.md` — caching and rate-limiting in front of Vectorize
- `documentation/categories/patterns/rag-architecture-2026.md` — RAG topology
- `documentation/categories/patterns/multi-tenant-data-isolation.md` — namespaces vs per-tenant databases

## Source URLs (verified 2026-08-09)

- Vectorize metadata filtering — https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
- Vectorize llms-full.txt — https://developers.cloudflare.com/vectorize/llms-full.txt
- Vectorize best practices (insert-vectors) — https://developers.cloudflare.com/vectorize/best-practices/insert-vectors/
- AI Search release notes — https://developers.cloudflare.com/ai-search/platform/release-note/
- AI Search changelog — https://developers.cloudflare.com/changelog/product/ai-search/
