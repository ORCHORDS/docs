# Locale-Aware Search Ranking with Cloudflare Vectorize Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Multilingual search results rank poorly when a single embedding model scores documents without
regard to the query language. A Spanish query retrieves English-biased results because the vector
index mixes languages into one undifferentiated space. Teams need per-locale relevance with no
round-trip to an external search engine.

---

## Context

Cloudflare Vectorize provides a managed ANN (approximate nearest-neighbour) index that lives at
the edge. Combining it with Workers AI embedding models and locale metadata stored in D1 lets you
build a fully edge-native multilingual semantic search. The key insight is that language-specific
namespacing of index rows—via metadata filters—keeps locale spaces separated without requiring
separate Vectorize indexes for each locale.

Supported embedding models on Workers AI (`@cf/baai/bge-*`) are multilingual but benefit from
language-scoped retrieval because dot-product similarity still cross-contaminates languages that
share vocabulary.

---

## 1. Embedding Documents at Ingest

Each document receives an embedding tagged with its `locale` metadata field. Metadata filters in
Vectorize then restrict retrieval to the caller's locale.

```typescript
// worker/ingest.ts
interface DocPayload {
  id: string;
  locale: string;     // BCP-47: "es", "fr", "ja"
  text: string;
  title: string;
}

export async function ingestDocument(
  env: Env,
  doc: DocPayload
): Promise<void> {
  const embeddingRes = await env.AI.run('@cf/baai/bge-large-en-v1.5', {
    text: [doc.text],
  });

  const vector = embeddingRes.data[0];

  await env.VECTORIZE.upsert([
    {
      id: doc.id,
      values: vector,
      metadata: {
        locale: doc.locale,
        title: doc.title,
        docId: doc.id,
      },
    },
  ]);
}
```

---

## 2. Locale-Scoped Query

The query embedding is generated from the raw search string. The `filter` parameter restricts
Vectorize to vectors whose `locale` metadata matches the request locale, so cross-language
contamination is eliminated at the index level.

```typescript
// worker/search.ts
export async function localeSearch(
  env: Env,
  query: string,
  locale: string,           // resolved BCP-47 tag
  topK = 10
): Promise<VectorizeMatch[]> {
  const queryEmbed = await env.AI.run('@cf/baai/bge-large-en-v1.5', {
    text: [query],
  });

  const results = await env.VECTORIZE.query(queryEmbed.data[0], {
    topK,
    filter: { locale },       // metadata equality filter
    returnMetadata: 'all',
  });

  return results.matches;
}
```

---

## 3. Score Boosting with Locale-Specific Signals

Raw cosine similarity does not account for recency, popularity, or locale-specific editorial
boosts stored in D1. Apply a weighted re-ranking pass after retrieval.

```typescript
// worker/rerank.ts
interface D1DocRow {
  id: string;
  editorial_boost: number;  // 0.0–1.0, set by content editors per locale
  published_at: string;     // ISO-8601
}

export async function rerank(
  env: Env,
  matches: VectorizeMatch[],
  locale: string
): Promise<VectorizeMatch[]> {
  const ids = matches.map((m) => m.id);
  const placeholders = ids.map(() => '?').join(',');

  const { results } = await env.DB.prepare(
    `SELECT id, editorial_boost, published_at
     FROM documents
     WHERE id IN (${placeholders}) AND locale = ?`
  )
    .bind(...ids, locale)
    .all<D1DocRow>();

  const boostMap = new Map(
    results.map((r) => [r.id, r.editorial_boost ?? 0])
  );

  const RECENCY_WEIGHT = 0.1;
  const now = Date.now();

  return matches
    .map((m) => {
      const boost = boostMap.get(m.id) ?? 0;
      const row = results.find((r) => r.id === m.id);
      const ageMs = row
        ? now - new Date(row.published_at).getTime()
        : Infinity;
      const recencyScore = Math.exp(-ageMs / (1000 * 60 * 60 * 24 * 30)); // 30-day half-life
      const finalScore =
        (m.score ?? 0) * (1 + boost) + RECENCY_WEIGHT * recencyScore;
      return { ...m, score: finalScore };
    })
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
}
```

---

## 4. Locale Resolution Middleware

Accept-Language negotiation happens before search to avoid per-query resolution overhead.

```typescript
// worker/locale.ts
const SUPPORTED = ['en', 'es', 'fr', 'de', 'ja', 'ar', 'sw'];
const DEFAULT_LOCALE = 'en';

export function resolveLocale(request: Request): string {
  const cfLocale = (request as any).cf?.acceptLanguage as string | undefined;
  const header = request.headers.get('Accept-Language') ?? '';
  const source = cfLocale ?? header;

  for (const tag of source.split(',')) {
    const lang = tag.trim().split(';')[0].split('-')[0].toLowerCase();
    if (SUPPORTED.includes(lang)) return lang;
  }
  return DEFAULT_LOCALE;
}
```

---

## 5. Composing the Search Handler

```typescript
// worker/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (new URL(request.url).pathname !== '/search') {
      return new Response('Not found', { status: 404 });
    }

    const { searchParams } = new URL(request.url);
    const q = searchParams.get('q')?.trim();
    if (!q) return new Response('Missing q', { status: 400 });

    const locale = resolveLocale(request);
    const raw = await localeSearch(env, q, locale);
    const ranked = await rerank(env, raw, locale);

    return Response.json({
      locale,
      results: ranked.map((m) => ({
        id: m.id,
        title: m.metadata?.title,
        score: m.score,
      })),
    });
  },
};
```

---

## Anti-patterns

- **Single shared Vectorize index with no metadata filter** — retrieval score silently degrades for
  minority-language queries because vectors from high-resource languages dominate the ANN graph.
- **Embedding the locale tag inside the text** — prepending `"[es]"` to the string before embedding
  pollutes the vector space and does not reliably isolate languages.
- **Re-embedding the query on every request with no caching** — embedding calls are billed per
  token; cache short repeated queries in Workers KV with a short TTL.
- **Storing all locale metadata as a single concatenated string** — Vectorize metadata filters only
  support equality and `$in` operators; use a flat `locale` field, not `"locale:es,fr"`.

---

## Gotchas

- Vectorize `filter` is applied before scoring, not after. The `topK` limit applies to the
  already-filtered subset. For small locales, `topK` may return fewer than requested results.
- Workers AI embedding dimensions must match the Vectorize index dimension set at creation time.
  `bge-large-en-v1.5` outputs 1024 dimensions; `bge-base-en-v1.5` outputs 768. They cannot share
  an index.
- Metadata values are stored as strings in Vectorize. Cast numeric boosts to string at ingest and
  parse them back in rerank logic if retrieved via metadata.
- Vectorize upsert is eventually consistent; freshly ingested documents may not appear in query
  results for up to a few seconds.

---

## Verification

```bash
# Ingest a Spanish document
curl -X POST https://my-worker.example.com/ingest \
  -H "Content-Type: application/json" \
  -d '{"id":"doc-1","locale":"es","text":"El clima es cálido hoy","title":"El tiempo"}'

# Query in Spanish — should return doc-1 at top
curl "https://my-worker.example.com/search?q=temperatura+hoy" \
  -H "Accept-Language: es"

# Query in English — should NOT return doc-1 (different locale filter)
curl "https://my-worker.example.com/search?q=today+weather" \
  -H "Accept-Language: en"
```

---

## Related

- `translation-memory-semantic-vectorize-workers.md`
- `language-detection-workers-accept-language.md`
- `kv-locale-key-sharding-high-traffic.md`
- `d1-fts5-multilingual-tokenizer-configuration.md`

---

## Sources

- Cloudflare Vectorize documentation — https://developers.cloudflare.com/vectorize/
- Cloudflare Workers AI — https://developers.cloudflare.com/workers-ai/
- BAAI BGE model card — https://huggingface.co/BAAI/bge-large-en-v1.5
- Unicode CLDR language subtag registry — https://www.iana.org/assignments/language-subtag-registry
