# Vectorize Metadata Filtering with Complex Predicates

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
Naive Vectorize queries return semantically similar vectors regardless of tenant, date range, content category, or access tier. Without metadata filtering, multi-tenant systems leak cross-tenant results, and time-bounded queries require expensive post-hoc filtering in application code after retrieving more vectors than needed.

## Context
Vectorize supports a subset of MongoDB-style filter predicates on indexed metadata fields. Filters are pushed down into the ANN search, reducing both result count and RU consumption. As of mid-2026, supported operators include `$eq`, `$ne`, `$in`, `$nin`, `$lt`, `$lte`, `$gt`, `$gte`, and logical combinators `$and`, `$or`. Fields must be declared as `indexed` at index creation time; querying non-indexed fields silently returns unfiltered results. This article documents complex predicate patterns, performance trade-offs, and common pitfalls.

## Index Creation with Indexed Metadata Fields

Declare metadata fields at index creation. Only declared fields support push-down filtering.

```bash
# wrangler CLI — create index with typed metadata fields
wrangler vectorize create documents \
  --dimensions 768 \
  --metric cosine \
  --metadata-indexes \
    tenantId:string \
    contentType:string \
    tier:number \
    publishedAt:number \
    language:string \
    isPublic:boolean
```

Or via `wrangler.toml`:

```toml
[[vectorize]]
binding = "VECTORIZE"
index_name = "documents"
dimensions = 768
metric = "cosine"

[[vectorize.metadata_indexes]]
property_name = "tenantId"
index_type = "string"

[[vectorize.metadata_indexes]]
property_name = "contentType"
index_type = "string"

[[vectorize.metadata_indexes]]
property_name = "tier"
index_type = "number"

[[vectorize.metadata_indexes]]
property_name = "publishedAt"
index_type = "number"

[[vectorize.metadata_indexes]]
property_name = "isPublic"
index_type = "boolean"
```

## Predicate Pattern Library

```typescript
// filter-patterns.ts
import type { VectorizeIndex } from '@cloudflare/workers-types';

interface QueryOptions {
  topK?: number;
  returnMetadata?: 'all' | 'indexed' | 'none';
}

// ─── 1. Tenant isolation (equality) ─────────────────────────────────────────
export async function queryForTenant(
  index: VectorizeIndex,
  vec: number[],
  tenantId: string,
  opts: QueryOptions = {},
) {
  return index.query(vec, {
    topK: opts.topK ?? 10,
    returnMetadata: opts.returnMetadata ?? 'indexed',
    filter: { tenantId: { $eq: tenantId } },
  });
}

// ─── 2. Date range (epoch seconds stored as number) ─────────────────────────
export async function queryDateRange(
  index: VectorizeIndex,
  vec: number[],
  fromEpoch: number,
  toEpoch: number,
  opts: QueryOptions = {},
) {
  return index.query(vec, {
    topK: opts.topK ?? 10,
    returnMetadata: opts.returnMetadata ?? 'indexed',
    filter: {
      publishedAt: { $gte: fromEpoch, $lte: toEpoch },
    },
  });
}

// ─── 3. Multi-tenant with content type allowlist ─────────────────────────────
export async function queryTenantContentTypes(
  index: VectorizeIndex,
  vec: number[],
  tenantId: string,
  allowedTypes: string[],
  opts: QueryOptions = {},
) {
  return index.query(vec, {
    topK: opts.topK ?? 10,
    returnMetadata: 'indexed',
    filter: {
      $and: [
        { tenantId: { $eq: tenantId } },
        { contentType: { $in: allowedTypes } },
      ],
    },
  });
}

// ─── 4. Tiered access control ────────────────────────────────────────────────
export async function queryByAccessTier(
  index: VectorizeIndex,
  vec: number[],
  maxTier: number, // user's tier; return only content at or below this tier
  opts: QueryOptions = {},
) {
  return index.query(vec, {
    topK: opts.topK ?? 10,
    returnMetadata: 'indexed',
    filter: {
      tier: { $lte: maxTier },
    },
  });
}

// ─── 5. Exclude content types (denylist) ────────────────────────────────────
export async function queryExcludeTypes(
  index: VectorizeIndex,
  vec: number[],
  excludedTypes: string[],
  opts: QueryOptions = {},
) {
  return index.query(vec, {
    topK: opts.topK ?? 10,
    returnMetadata: 'indexed',
    filter: {
      contentType: { $nin: excludedTypes },
    },
  });
}

// ─── 6. Combined: tenant + date range + content type + tier ─────────────────
export async function queryComplex(
  index: VectorizeIndex,
  vec: number[],
  params: {
    tenantId: string;
    fromEpoch: number;
    toEpoch: number;
    allowedTypes: string[];
    maxTier: number;
  },
  opts: QueryOptions = {},
) {
  const { tenantId, fromEpoch, toEpoch, allowedTypes, maxTier } = params;
  return index.query(vec, {
    topK: opts.topK ?? 10,
    returnMetadata: 'all',
    filter: {
      $and: [
        { tenantId: { $eq: tenantId } },
        { publishedAt: { $gte: fromEpoch, $lte: toEpoch } },
        { contentType: { $in: allowedTypes } },
        { tier: { $lte: maxTier } },
      ],
    },
  });
}

// ─── 7. Public content OR owned private content ──────────────────────────────
export async function queryPublicOrOwned(
  index: VectorizeIndex,
  vec: number[],
  tenantId: string,
  opts: QueryOptions = {},
) {
  return index.query(vec, {
    topK: opts.topK ?? 10,
    returnMetadata: 'indexed',
    filter: {
      $or: [
        { isPublic: { $eq: true } },
        { tenantId: { $eq: tenantId } },
      ],
    },
  });
}
```

## Upsert Helpers: Consistent Metadata Shapes

Always store epoch seconds as `number` (not ISO strings) for range filter compatibility:

```typescript
// upsert-helpers.ts
import type { VectorizeIndex } from '@cloudflare/workers-types';

interface DocumentMetadata {
  docId: string;
  tenantId: string;
  contentType: 'article' | 'faq' | 'policy' | 'product';
  tier: 0 | 1 | 2; // 0 = public, 1 = pro, 2 = enterprise
  publishedAt: Date;
  language: string;
  isPublic: boolean;
}

export async function upsertDocument(
  index: VectorizeIndex,
  id: string,
  vec: number[],
  meta: DocumentMetadata,
): Promise<void> {
  await index.upsert([
    {
      id,
      values: vec,
      metadata: {
        docId: meta.docId,
        tenantId: meta.tenantId,
        contentType: meta.contentType,
        tier: meta.tier,
        // Store as Unix epoch (seconds) for numeric range filters
        publishedAt: Math.floor(meta.publishedAt.getTime() / 1000),
        language: meta.language,
        isPublic: meta.isPublic,
      },
    },
  ]);
}
```

## Worker: Full Filter-Aware RAG Query Handler

```typescript
// rag-filtered.ts
import type { VectorizeIndex, Ai } from '@cloudflare/workers-types';
import { queryComplex } from './filter-patterns';

interface Env {
  VECTORIZE: VectorizeIndex;
  AI: Ai;
}

interface FilteredRagRequest {
  query: string;
  tenantId: string;
  contentTypes: string[];
  maxTier: number;
  daysBack: number;
  topK?: number;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const body = (await req.json()) as FilteredRagRequest;
    const {
      query, tenantId, contentTypes, maxTier, daysBack, topK = 8,
    } = body;

    // Embed query
    const embResp = await env.AI.run('@cf/baai/bge-base-en-v1.5', {
      text: [query],
    });
    const queryVec = (embResp as { data: number[][] }).data[0];

    const nowEpoch = Math.floor(Date.now() / 1000);
    const fromEpoch = nowEpoch - daysBack * 86400;

    // Filtered ANN search
    const results = await queryComplex(
      env.VECTORIZE,
      queryVec,
      {
        tenantId,
        fromEpoch,
        toEpoch: nowEpoch,
        allowedTypes: contentTypes,
        maxTier,
      },
      { topK },
    );

    if (results.matches.length === 0) {
      return Response.json({ answer: 'No relevant content found.', sources: [] });
    }

    // Build context for LLM
    const context = results.matches
      .map((m, i) => {
        const meta = m.metadata as { snippet?: string; docId?: string };
        return `[${i + 1}] ${meta.snippet ?? '(no snippet)'} (doc: ${meta.docId ?? 'unknown'})`;
      })
      .join('\n');

    const completion = await env.AI.run('@cf/meta/llama-3.1-8b-instruct', {
      messages: [
        {
          role: 'system',
          content: 'Answer from the context below. Be concise. Cite source numbers.',
        },
        { role: 'user', content: `Context:\n${context}\n\nQuestion: ${query}` },
      ],
    });

    const answer = (completion as { response?: string }).response ?? '';
    const sources = results.matches.map(m => (m.metadata as Record<string, unknown>).docId ?? m.id);

    return Response.json({ answer, sources, matchCount: results.matches.length });
  },
} satisfies ExportedHandler<Env>;
```

## Filter Performance Trade-offs

| Filter selectivity | Behaviour |
|---|---|
| High (e.g. exact tenantId on a 1 M index) | ANN candidate pool shrinks; faster, lower recall on edge cases |
| Low (e.g. `tier: { $lte: 2 }` on all tiers) | ANN pool stays large; effectively no benefit over unfiltered |
| Combined `$and` (tenant + date + type) | Best trade-off; each predicate reduces the candidate pool independently |
| `$or` across two large sets | Merges pools; can be slower than two separate queries |

## Anti-patterns

- **Storing dates as ISO strings** — string comparison (`$lt: "2026-08-01"`) does not sort correctly across year boundaries; always use epoch seconds (`number`).
- **Filtering on non-indexed fields** — Vectorize silently ignores filters on non-indexed fields and returns unfiltered results; verify index schema with `wrangler vectorize describe`.
- **Using `$or` across all tenant IDs to implement "shared content"** — `$or` with a large `$in` list is slow; store a synthetic `isPublic: true` flag and use `$or: [isPublic, tenantId]` instead.
- **Fetching `topK: 100` then filtering in the Worker** — always push filters into Vectorize rather than over-fetching and discarding; push-down is 3–10× cheaper in RUs.
- **Nesting `$and` inside `$or` more than 2 levels deep** — Vectorize filter depth is limited; flatten predicates or pre-compute composite metadata fields.

## Gotchas

- `returnMetadata: 'indexed'` returns only declared indexed fields — use `'all'` to also get non-indexed fields like `snippet` or `body`.
- The `filter` parameter must be a plain JSON object serialisable to a Vectorize-compatible predicate; JavaScript `Date` objects or `undefined` values will cause silent failures.
- Vectorize ANN uses approximate search; a very selective filter that matches fewer than `topK * 5` vectors may return fewer results than `topK` even when semantically relevant matches exist — increase `topK` and trim post-query.
- `wrangler vectorize describe <index>` shows declared metadata indexes; verify your field names and types match before debugging filter silences.
- Adding new indexed metadata fields to an existing index requires reindexing — upsert all vectors again with the new field populated.

## Verification

```bash
# 1. Describe index and verify indexed fields
wrangler vectorize describe documents

# 2. Query with tenant filter and confirm cross-tenant exclusion
curl -X POST https://<worker>/rag \
  -H 'Content-Type: application/json' \
  -d '{"query":"refund policy","tenantId":"acme","contentTypes":["policy"],"maxTier":1,"daysBack":90}'

# All returned docIds should have tenantId == "acme" in their metadata

# 3. Verify date range filter
# Insert a vector with publishedAt = 10 years ago
# Query with daysBack = 30 — that vector must NOT appear in results
```

## Related

- `metadata-filtering-vectors.md`
- `vectorize-multi-tenant-namespace-partitioning.md`
- `vectorize-batch-upsert-incremental-sync.md`
- `retrieval-augmented-generation-d1-vectorize.md`
- `vectorize-multi-vector-late-interaction.md`

## Sources

- https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
- https://developers.cloudflare.com/vectorize/get-started/
- https://developers.cloudflare.com/vectorize/reference/client-api/
