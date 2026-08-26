# Building a Translation Memory with D1 and Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A localization pipeline re-translates segments that have already been translated before, wasting API calls and producing inconsistent terminology. A translation memory (TM) should return an exact or fuzzy match from previous translations before calling a machine-translation API. The challenge is implementing exact-match lookup, fuzzy trigram scoring, semantic vector fallback, and a quality-estimation gate — all inside a Cloudflare Worker with D1 as the backing store and KV as a cache layer.

## Context

A translation memory stores pairs of source segments and their approved translations. An exact match (100% TM hit) is a hash lookup. A fuzzy match (typically 70–99%) uses string similarity — trigram overlap is fast and works well for short segments. For semantically equivalent but lexically different segments ("Buy now" vs. "Purchase today"), a vector similarity search with Cloudflare Vectorize provides recall that trigrams miss. Workers AI can score low-confidence TM hits before surfacing them, acting as a lightweight quality-estimation (QE) step. KV caches exact-match results for hot segments to avoid D1 reads on every request.

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS segments (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  source_hash  TEXT    NOT NULL,          -- SHA-256 of normalized source text
  source_text  TEXT    NOT NULL,
  target_text  TEXT    NOT NULL,
  locale       TEXT    NOT NULL,          -- target locale, e.g. "de-DE"
  domain       TEXT    NOT NULL DEFAULT 'general', -- product area
  quality      REAL    NOT NULL DEFAULT 1.0,       -- 0.0–1.0 QE score
  last_used    INTEGER NOT NULL DEFAULT (unixepoch()),
  created_at   INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE UNIQUE INDEX idx_segments_hash_locale
  ON segments(source_hash, locale, domain);

CREATE INDEX idx_segments_locale_domain
  ON segments(locale, domain);

-- Trigram helper: store 3-char substrings for fuzzy lookup
CREATE TABLE IF NOT EXISTS trigrams (
  segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
  trigram    TEXT    NOT NULL
);

CREATE INDEX idx_trigrams_trigram ON trigrams(trigram);
```

## Exact-Match Lookup via `source_hash`

```typescript
// utils/tm.ts
import { sha256Hex } from './crypto';

export async function exactMatch(
  db: D1Database,
  kv: KVNamespace,
  sourceText: string,
  locale: string,
  domain = 'general'
): Promise<string | null> {
  const normalized = sourceText.trim().toLowerCase();
  const hash = await sha256Hex(normalized);
  const cacheKey = `tm:exact:${locale}:${domain}:${hash}`;

  // 1. KV cache
  const cached = await kv.get(cacheKey);
  if (cached) return cached;

  // 2. D1 lookup
  const row = await db
    .prepare(
      `SELECT target_text FROM segments
       WHERE source_hash = ? AND locale = ? AND domain = ?
       ORDER BY quality DESC, last_used DESC
       LIMIT 1`
    )
    .bind(hash, locale, domain)
    .first<{ target_text: string }>();

  if (!row) return null;

  // 3. Update last_used and cache the hit
  await db
    .prepare('UPDATE segments SET last_used = unixepoch() WHERE source_hash = ? AND locale = ? AND domain = ?')
    .bind(hash, locale, domain)
    .run();

  await kv.put(cacheKey, row.target_text, { expirationTtl: 3600 });
  return row.target_text;
}

// Simple SHA-256 helper using the Web Crypto API (available in Workers)
async function sha256Hex(text: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(text)
  );
  return Array.from(new Uint8Array(buf))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}
```

## Fuzzy Match Using Trigram Similarity

```typescript
// utils/trigram.ts

/** Extract all 3-character substrings from a string. */
export function extractTrigrams(text: string): Set<string> {
  const s = ` ${text.toLowerCase()} `; // pad for edge n-grams
  const grams = new Set<string>();
  for (let i = 0; i <= s.length - 3; i++) {
    grams.add(s.slice(i, i + 3));
  }
  return grams;
}

/** Jaccard similarity between two trigram sets. */
export function trigramSimilarity(a: Set<string>, b: Set<string>): number {
  let intersection = 0;
  for (const g of a) if (b.has(g)) intersection++;
  const union = a.size + b.size - intersection;
  return union === 0 ? 1 : intersection / union;
}

/**
 * Fuzzy lookup: finds candidate segments sharing at least MIN_SHARED trigrams
 * with the query, then scores them by Jaccard similarity.
 */
export async function fuzzyMatch(
  db: D1Database,
  sourceText: string,
  locale: string,
  domain = 'general',
  threshold = 0.7
): Promise<{ target_text: string; score: number } | null> {
  const queryGrams = extractTrigrams(sourceText);
  const gramList = [...queryGrams];

  if (gramList.length === 0) return null;

  // Find candidate segment IDs that share at least one trigram
  const placeholders = gramList.map(() => '?').join(',');
  const { results: candidates } = await db
    .prepare(
      `SELECT DISTINCT t.segment_id, s.source_text, s.target_text
       FROM trigrams t
       JOIN segments s ON s.id = t.segment_id
       WHERE t.trigram IN (${placeholders})
         AND s.locale = ? AND s.domain = ?
       LIMIT 50`
    )
    .bind(...gramList, locale, domain)
    .all<{ segment_id: number; source_text: string; target_text: string }>();

  let best: { target_text: string; score: number } | null = null;

  for (const row of candidates) {
    const candidateGrams = extractTrigrams(row.source_text);
    const score = trigramSimilarity(queryGrams, candidateGrams);
    if (score >= threshold && (!best || score > best.score)) {
      best = { target_text: row.target_text, score };
    }
  }

  return best;
}
```

## Vectorize Cosine-Similarity Fallback

```typescript
// utils/vectorFallback.ts

export interface Env {
  AI: Ai;
  VECTORIZE: VectorizeIndex;
  DB: D1Database;
}

/**
 * Embeds the source text and queries Vectorize for semantically similar segments.
 * Returns the best match above the cosine threshold.
 */
export async function vectorFallback(
  env: Env,
  sourceText: string,
  locale: string,
  threshold = 0.85
): Promise<string | null> {
  // 1. Embed the query
  const embedResult = await env.AI.run('@cf/baai/bge-small-en-v1.5', {
    text: [sourceText],
  }) as { data: number[][] };
  const queryVector = embedResult.data[0];

  // 2. Query Vectorize
  const matches = await env.VECTORIZE.query(queryVector, {
    topK: 5,
    filter: { locale, namespace: locale },
    returnMetadata: 'all',
  });

  const top = matches.matches.find(m => m.score >= threshold);
  if (!top?.id) return null;

  // 3. Fetch the actual target text from D1 by segment ID
  const row = await env.DB
    .prepare('SELECT target_text FROM segments WHERE id = ?')
    .bind(Number(top.id))
    .first<{ target_text: string }>();

  return row?.target_text ?? null;
}
```

## Workers AI Quality-Estimation Gate

Before surfacing a low-confidence fuzzy or vector TM hit (score < 0.90), run a lightweight QE step:

```typescript
export async function qualityEstimate(
  ai: Ai,
  sourceText: string,
  targetText: string
): Promise<number> {
  // Use a multilingual model to score translation adequacy 0–1
  const prompt = [
    { role: 'system', content: 'You are a translation quality estimator. Respond with ONLY a decimal score from 0.0 to 1.0 indicating how well the translation preserves the meaning of the source.' },
    { role: 'user', content: `Source: ${sourceText}\nTranslation: ${targetText}\nScore:` },
  ];
  const result = await ai.run('@cf/meta/llama-3-8b-instruct', { messages: prompt }) as { response: string };
  const score = parseFloat(result.response.trim());
  return isNaN(score) ? 0 : Math.min(1, Math.max(0, score));
}
```

## Main Worker Request Handler

```typescript
// worker.ts
import { exactMatch } from './utils/tm';
import { fuzzyMatch } from './utils/trigram';
import { vectorFallback } from './utils/vectorFallback';
import { qualityEstimate } from './utils/qe';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { source, locale, domain = 'general' } = await request.json<{
      source: string; locale: string; domain?: string;
    }>();

    if (!source || !locale) {
      return Response.json({ error: 'Missing source or locale' }, { status: 400 });
    }

    // 1. Exact match (hash)
    const exact = await exactMatch(env.DB, env.TM_CACHE, source, locale, domain);
    if (exact) return Response.json({ translation: exact, matchType: 'exact', score: 1.0 });

    // 2. Fuzzy trigram match
    const fuzzy = await fuzzyMatch(env.DB, source, locale, domain, 0.7);
    if (fuzzy && fuzzy.score >= 0.9) {
      return Response.json({ translation: fuzzy.target_text, matchType: 'fuzzy', score: fuzzy.score });
    }

    // 3. Vectorize semantic fallback
    const vector = await vectorFallback(env, source, locale, 0.85);
    if (vector) {
      const qe = await qualityEstimate(env.AI, source, vector);
      if (qe >= 0.75) {
        return Response.json({ translation: vector, matchType: 'semantic', score: qe });
      }
    }

    // 4. No TM hit — caller should invoke MT API
    return Response.json({ translation: null, matchType: 'none', score: 0 }, { status: 404 });
  },
};
```

## Anti-patterns

- **Using `LIKE '%keyword%'` for fuzzy search in D1** — full-table scan; does not scale beyond a few thousand rows and has no similarity score.
- **Skipping the QE gate for low-confidence matches** — surfacing a 70% fuzzy match without QE risks inserting incorrect translations into published content.
- **Embedding every lookup in real time** — Vectorize queries require an embedding inference call; use it only as a third-tier fallback after hash and trigram checks.
- **Ignoring the `domain` field** — "Settings" in a UI context means something different than "Settings" in an audio-engineering context; always scope TM lookups by domain.

## Gotchas

- The `crypto.subtle.digest()` call in Workers is async and must be awaited; it is not synchronous like Node.js `crypto.createHash()`.
- Vectorize `query()` returns matches sorted by descending score; the `filter` object uses metadata fields set at `upsert` time — ensure you set `locale` as metadata when indexing segments.
- D1 `IN (?,?,...)` has a maximum of ~999 placeholders per SQLite statement; cap trigram lists to 200 unique grams before querying.
- Workers AI `@cf/baai/bge-small-en-v1.5` produces 384-dimensional embeddings; your Vectorize index must be created with `dimensions: 384` and `metric: cosine`.

## Verification

```bash
# Insert a test segment
curl -X POST https://my-worker.example.workers.dev/tm/insert \
  -H 'Content-Type: application/json' \
  -d '{"source":"Save changes","target":"Änderungen speichern","locale":"de-DE","domain":"ui"}'

# Exact match
curl -X POST https://my-worker.example.workers.dev/tm/lookup \
  -H 'Content-Type: application/json' \
  -d '{"source":"Save changes","locale":"de-DE","domain":"ui"}'
# Expected: {"translation":"Änderungen speichern","matchType":"exact","score":1}

# Fuzzy match (minor variation)
curl -X POST https://my-worker.example.workers.dev/tm/lookup \
  -H 'Content-Type: application/json' \
  -d '{"source":"Save your changes","locale":"de-DE","domain":"ui"}'
# Expected: matchType "fuzzy" with score ~0.75

# Verify D1 row count
npx wrangler d1 execute MY_DB \
  --command 'SELECT COUNT(*) as total FROM segments WHERE locale = "de-DE"'
```

## Related

- `locale-aware-number-parsing-validation-workers.md`
- `locale-aware-sorting-d1-sqlite-icu.md`
- `intl-relativetimeformat-edge-localization-workers.md`

## Sources

- Cloudflare Vectorize — https://developers.cloudflare.com/vectorize/
- Cloudflare Workers AI — https://developers.cloudflare.com/workers-ai/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Trigram similarity (PostgreSQL docs, pg_trgm) — https://www.postgresql.org/docs/current/pgtrgm.html
- LISA TM Exchange standard — https://www.gala-global.org/tmx
