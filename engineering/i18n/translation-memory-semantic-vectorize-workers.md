# Semantic Translation Memory with Cloudflare Vectorize

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Translators repeatedly translate near-identical strings (e.g. "Add to cart" vs "Add item to cart")
from scratch because the traditional translation memory (TM) fuzzy-match threshold rejects strings
below 75% character-level similarity, wasting time and creating inconsistent terminology.

## Context
Semantic TM replaces edit-distance fuzzy matching with embedding-based similarity search. Source
strings are embedded into a dense vector using Workers AI (`@cf/baai/bge-base-en-v1.5`), then stored
in Cloudflare Vectorize. At translation time, the new string's embedding is queried against the index
to retrieve the most semantically similar past translations. A Cloudflare Worker exposes this as an
HTTP API consumed by the TMS webhook or a VS Code i18n extension. D1 stores the translation pairs
and metadata; Vectorize stores only the vector and a reference ID.

## Schema: D1 Translation Store

```sql
-- Run via wrangler d1 execute
CREATE TABLE IF NOT EXISTS translation_units (
  id          TEXT PRIMARY KEY,         -- UUID
  source_lang TEXT NOT NULL,            -- BCP 47, e.g. "en"
  target_lang TEXT NOT NULL,            -- BCP 47, e.g. "de"
  source_text TEXT NOT NULL,
  target_text TEXT NOT NULL,
  domain      TEXT,                     -- e.g. "ecommerce", "legal"
  created_at  INTEGER NOT NULL,         -- Unix ms
  score       REAL                      -- BLEU or human rating 0-1
);
CREATE INDEX idx_tu_domain ON translation_units(domain, source_lang, target_lang);
```

## Embedding and Indexing a Translation Unit

When a translator approves a translation, the Worker embeds the source string with Workers AI and
upserts the vector into Vectorize.

```typescript
// embed.ts
export async function embedText(ai: Ai, text: string): Promise<number[]> {
  const response = await ai.run("@cf/baai/bge-base-en-v1.5", {
    text: [text],
  });
  return response.data[0];
}

export async function indexTranslationUnit(
  id: string,
  sourceText: string,
  domain: string,
  ai: Ai,
  vectorize: VectorizeIndex
): Promise<void> {
  const vector = await embedText(ai, sourceText);
  await vectorize.upsert([
    {
      id,
      values: vector,
      metadata: { domain },
    },
  ]);
}
```

## Ingestion Route: POST /tm/units

```typescript
// ingest-route.ts
import { v4 as uuid } from "uuid";
import { embedText, indexTranslationUnit } from "./embed";

interface IngestBody {
  source_lang: string;
  target_lang: string;
  source_text: string;
  target_text: string;
  domain?: string;
  score?: number;
}

export async function handleIngest(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<IngestBody>();
  if (!body.source_text || !body.target_text || !body.source_lang || !body.target_lang) {
    return Response.json({ error: "missing required fields" }, { status: 400 });
  }

  const id = uuid();
  const now = Date.now();

  await env.DB.prepare(
    `INSERT INTO translation_units (id, source_lang, target_lang, source_text, target_text, domain, created_at, score)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  )
    .bind(id, body.source_lang, body.target_lang, body.source_text, body.target_text,
          body.domain ?? null, now, body.score ?? null)
    .run();

  await indexTranslationUnit(id, body.source_text, body.domain ?? "general", env.AI, env.VECTORIZE);

  return Response.json({ id }, { status: 201 });
}
```

## Query Route: POST /tm/lookup

Embed the new source string, query Vectorize for the top-k nearest neighbours, and hydrate with
full translation pairs from D1.

```typescript
// lookup-route.ts
import { embedText } from "./embed";

interface LookupBody {
  source_text: string;
  source_lang: string;
  target_lang: string;
  domain?: string;
  top_k?: number;
  min_score?: number;
}

export interface TmMatch {
  id: string;
  source_text: string;
  target_text: string;
  semantic_score: number;
  tm_score: number | null;
  domain: string | null;
}

export async function handleLookup(
  request: Request,
  env: Env
): Promise<Response> {
  const body = await request.json<LookupBody>();
  const topK = Math.min(body.top_k ?? 5, 20);
  const minScore = body.min_score ?? 0.75;

  const vector = await embedText(env.AI, body.source_text);

  const results = await env.VECTORIZE.query(vector, {
    topK,
    filter: body.domain ? { domain: body.domain } : undefined,
    returnMetadata: "none",
  });

  const candidates = results.matches.filter(m => m.score >= minScore);
  if (candidates.length === 0) {
    return Response.json({ matches: [] });
  }

  const placeholders = candidates.map(() => "?").join(", ");
  const ids = candidates.map(c => c.id);

  const rows = await env.DB.prepare(
    `SELECT id, source_text, target_text, domain, score AS tm_score
     FROM translation_units
     WHERE id IN (${placeholders})
       AND source_lang = ? AND target_lang = ?`
  )
    .bind(...ids, body.source_lang, body.target_lang)
    .all<{ id: string; source_text: string; target_text: string; domain: string | null; tm_score: number | null }>();

  const scoreMap = new Map(candidates.map(c => [c.id, c.score]));
  const matches: TmMatch[] = rows.results.map(r => ({
    ...r,
    semantic_score: scoreMap.get(r.id) ?? 0,
  }));
  matches.sort((a, b) => b.semantic_score - a.semantic_score);

  return Response.json({ matches });
}
```

## Worker Entry: Routing

```typescript
// worker.ts
import { handleIngest } from "./ingest-route";
import { handleLookup } from "./lookup-route";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const auth = request.headers.get("Authorization");
    if (auth !== `Bearer ${env.TM_API_KEY}`) {
      return Response.json({ error: "unauthorized" }, { status: 401 });
    }

    if (request.method === "POST" && url.pathname === "/tm/units") {
      return handleIngest(request, env);
    }
    if (request.method === "POST" && url.pathname === "/tm/lookup") {
      return handleLookup(request, env);
    }
    return Response.json({ error: "not found" }, { status: 404 });
  },
};
```

## wrangler.toml Bindings

```toml
[[d1_databases]]
binding = "DB"
database_name = "tm-store"
database_id = "<your-d1-id>"

[[vectorize]]
binding = "VECTORIZE"
index_name = "tm-embeddings"
# Create with: wrangler vectorize create tm-embeddings --dimensions=768 --metric=cosine

[ai]
binding = "AI"

[vars]
TM_API_KEY = "replace-at-deploy-time"
```

## Anti-patterns
- Indexing target text instead of source text — semantic search must match on the source side only
- Using Vectorize `topK` > 20 without a `min_score` gate — returns unrelated pairs that confuse translators
- Skipping the D1 lookup and returning only Vectorize metadata — metadata is size-limited and stale
- Embedding full paragraphs — split at sentence level for meaningful similarity; paragraph vectors
  average out too many concepts
- Re-embedding on every request — cache embeddings for repeated source strings in a KV namespace with
  a content-hash key

## Gotchas
- `@cf/baai/bge-base-en-v1.5` is English-optimised; for multilingual source strings use
  `@cf/baai/bge-m3` (multilingual, 1024 dims — update Vectorize index dimensions accordingly)
- Vectorize cosine scores are in [0, 1]; a score of 0.85+ typically indicates a strong match but
  depends on your content domain — calibrate the `min_score` threshold on held-out data
- D1 `IN (?, ?, …)` placeholders must be injected dynamically — SQLite does not support array binding
- Workers AI requests count against your account's AI token budget; batch embedding calls where possible
- Vectorize index mutations are eventually consistent — newly upserted vectors may not appear in
  queries for up to 15 seconds

## Verification
1. Ingest "Add to cart" → "In den Warenkorb" (`en` → `de`), then query "Add item to basket"; assert
   the result's `semantic_score >= 0.82`.
2. Ingest 100 translation pairs and query each source string; assert P95 latency < 200 ms end-to-end.
3. Query with a completely unrelated domain string (e.g. a legal clause against an e-commerce TM);
   assert zero matches returned when `min_score = 0.75`.
4. Verify D1 row count equals Vectorize vector count after ingestion to detect partial failures.

## Related
- `/documentation/categories/i18n/translation-memory-2026.md`
- `/documentation/categories/i18n/translation-memory-tmx.md`
- `/documentation/categories/i18n/machine-translation-workers-ai-quality-scoring.md`
- `/documentation/categories/i18n/workers-queues-async-translation-pipeline.md`
- `/documentation/categories/i18n/translation-quality-metrics.md`

## Sources
- Cloudflare Vectorize: https://developers.cloudflare.com/vectorize/
- Workers AI model catalog: https://developers.cloudflare.com/workers-ai/models/
- BAAI/bge-base-en-v1.5: https://huggingface.co/BAAI/bge-base-en-v1.5
- Cloudflare D1: https://developers.cloudflare.com/d1/
- Translation Memory eXchange (TMX) standard: https://www.gala-global.org/tmx-14b
