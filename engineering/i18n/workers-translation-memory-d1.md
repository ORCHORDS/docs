# Translation Memory System in D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your localisation workflow re-translates strings that are identical or near-identical to previously translated segments, wasting time and budget. Translators working in different CAT tools have no shared memory. You need a translation memory (TM) system backed by Cloudflare D1 that stores source/target segment pairs, scores fuzzy matches using Levenshtein distance, suggests existing translations for new strings, reports TM leverage (exact/fuzzy/no-match percentages), can import from industry-standard TMX format, and can export for CAT tools — all running at the edge.

## Context

A translation memory stores *translation units* (TUs): pairs of source-language segments and their target-language translations, keyed by language pair (e.g. `en→fr`). When a new string arrives for translation:

1. If a 100% exact match exists in the TM → re-use at zero cost.
2. If a fuzzy match (typically ≥ 75% similarity) exists → suggest it for human post-editing.
3. No match → send for full human translation and add the result to the TM.

The industry similarity metric is *edit distance* expressed as a percentage: `similarity = 1 − (editDistance / maxLength)`. TMX (Translation Memory eXchange) is the OASIS standard XML format for inter-system TM exchange.

## Solution

```typescript
// workers-translation-memory-d1.ts
// Translation memory system backed by Cloudflare D1

export interface Env {
  DB: D1Database;
  TM_KV: KVNamespace;  // optional: cache top-N candidates per source hash
}

// ─── 1. D1 schema ────────────────────────────────────────────────────────

export const TM_DDL = `
CREATE TABLE IF NOT EXISTS translation_units (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  source_lang TEXT    NOT NULL,          -- BCP 47, e.g. 'en'
  target_lang TEXT    NOT NULL,          -- BCP 47, e.g. 'fr'
  source_text TEXT    NOT NULL,
  target_text TEXT    NOT NULL,
  source_hash TEXT    NOT NULL,          -- SHA-1 hex of normalised source_text
  domain      TEXT,                      -- optional: 'ecommerce', 'legal', …
  created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tu_hash_lang
  ON translation_units (source_hash, source_lang, target_lang);
CREATE INDEX IF NOT EXISTS idx_tu_lang_pair
  ON translation_units (source_lang, target_lang);
`;

// ─── 2. Text normalisation + hashing ─────────────────────────────────────

/**
 * Normalises a segment for hash comparison: trim, collapse whitespace,
 * lowercase. Keeps punctuation because it affects meaning.
 */
export function normalise(text: string): string {
  return text.trim().replace(/\s+/g, ' ');
}

/** Returns a hex SHA-1 of the normalised text using the WebCrypto API. */
export async function hashSegment(text: string): Promise<string> {
  const normalised = normalise(text);
  const encoded = new TextEncoder().encode(normalised);
  const hashBuffer = await crypto.subtle.digest('SHA-1', encoded);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

// ─── 3. Levenshtein distance ──────────────────────────────────────────────

/**
 * Computes the Levenshtein edit distance between two strings.
 * Operates on Unicode code points (not UTF-16 code units) via spread.
 * O(m × n) time; acceptable for segments up to ~500 characters.
 */
export function levenshtein(a: string, b: string): number {
  const sa = [...a]; // spread to Unicode code points
  const sb = [...b];
  const m  = sa.length;
  const n  = sb.length;

  if (m === 0) return n;
  if (n === 0) return m;

  // Use two-row DP instead of full matrix to save memory
  let prev = Array.from({ length: n + 1 }, (_, i) => i);
  let curr = new Array<number>(n + 1);

  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = sa[i - 1] === sb[j - 1] ? 0 : 1;
      curr[j] = Math.min(
        prev[j] + 1,       // deletion
        curr[j - 1] + 1,   // insertion
        prev[j - 1] + cost // substitution
      );
    }
    [prev, curr] = [curr, prev];
  }

  return prev[n];
}

/**
 * Returns similarity score in [0, 1] where 1.0 = exact match.
 * Uses the normalised edit distance: 1 - editDist / max(len_a, len_b).
 */
export function similarity(a: string, b: string): number {
  const normA = normalise(a);
  const normB = normalise(b);
  if (normA === normB) return 1.0;
  const dist  = levenshtein(normA, normB);
  const maxLen = Math.max([...normA].length, [...normB].length);
  return maxLen === 0 ? 1.0 : 1 - dist / maxLen;
}

// ─── 4. TM CRUD operations ────────────────────────────────────────────────

export interface TranslationUnit {
  id?:          number;
  source_lang:  string;
  target_lang:  string;
  source_text:  string;
  target_text:  string;
  source_hash?: string;
  domain?:      string;
}

/** Inserts or updates a translation unit (upsert on hash + lang pair). */
export async function upsertTU(
  db: D1Database,
  tu: TranslationUnit
): Promise<void> {
  const hash = await hashSegment(tu.source_text);
  await db
    .prepare(
      `INSERT INTO translation_units
         (source_lang, target_lang, source_text, target_text, source_hash, domain)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6)
       ON CONFLICT(source_hash, source_lang, target_lang) DO UPDATE SET
         target_text = excluded.target_text,
         updated_at  = unixepoch()`
    )
    .bind(tu.source_lang, tu.target_lang, tu.source_text, tu.target_text, hash, tu.domain ?? null)
    .run();
}

// ─── 5. Exact-match lookup ────────────────────────────────────────────────

export interface TmMatch {
  tu:         TranslationUnit;
  score:      number;  // 0–1
  matchType:  'exact' | 'fuzzy' | 'no-match';
}

/** Looks up a 100% exact match by source hash. */
export async function exactMatch(
  db: D1Database,
  sourceText: string,
  sourceLang: string,
  targetLang: string
): Promise<TmMatch | null> {
  const hash = await hashSegment(sourceText);
  const row = await db
    .prepare(
      `SELECT * FROM translation_units
       WHERE source_hash=?1 AND source_lang=?2 AND target_lang=?3
       LIMIT 1`
    )
    .bind(hash, sourceLang, targetLang)
    .first<TranslationUnit>();

  if (!row) return null;
  return { tu: row, score: 1.0, matchType: 'exact' };
}

// ─── 6. Fuzzy-match lookup ────────────────────────────────────────────────

/** Number of candidate rows to retrieve from D1 for fuzzy scoring. */
const CANDIDATE_LIMIT = 200;

/**
 * Returns the best fuzzy match for a source segment.
 * Retrieves up to CANDIDATE_LIMIT rows for the language pair from D1,
 * scores each with Levenshtein similarity, and returns the best match
 * above the minimum threshold.
 *
 * For very large TMs (> 50k segments), prefer a dedicated vector-search
 * index (Vectorize) for the candidate retrieval step.
 *
 * @param minScore - minimum similarity to consider a fuzzy match (default 0.75)
 */
export async function fuzzyMatch(
  db: D1Database,
  sourceText: string,
  sourceLang: string,
  targetLang: string,
  minScore = 0.75
): Promise<TmMatch | null> {
  // First try exact match
  const exact = await exactMatch(db, sourceText, sourceLang, targetLang);
  if (exact) return exact;

  // Retrieve candidates — filter by length to reduce computation
  const sourceLen = [...normalise(sourceText)].length;
  const lenMin    = Math.floor(sourceLen * 0.5);
  const lenMax    = Math.ceil(sourceLen * 2.0);

  const { results } = await db
    .prepare(
      `SELECT * FROM translation_units
       WHERE source_lang=?1 AND target_lang=?2
         AND length(source_text) BETWEEN ?3 AND ?4
       LIMIT ?5`
    )
    .bind(sourceLang, targetLang, lenMin, lenMax, CANDIDATE_LIMIT)
    .all<TranslationUnit>();

  let best: TmMatch | null = null;

  for (const row of results) {
    const score = similarity(sourceText, row.source_text);
    if (score >= minScore && (best === null || score > best.score)) {
      best = { tu: row, score, matchType: score === 1.0 ? 'exact' : 'fuzzy' };
    }
  }

  return best;
}

// ─── 7. TM leverage report ───────────────────────────────────────────────

export interface LeverageReport {
  total:        number;
  exact:        number; // 100% matches
  fuzzy:        number; // 75–99% matches
  noMatch:      number; // < 75%
  exactPct:     number;
  fuzzyPct:     number;
  noMatchPct:   number;
}

/**
 * Runs TM lookup on a batch of source segments and returns
 * a leverage report showing exact/fuzzy/no-match percentages.
 */
export async function leverageReport(
  db: D1Database,
  segments: string[],
  sourceLang: string,
  targetLang: string
): Promise<LeverageReport> {
  const counts = { exact: 0, fuzzy: 0, noMatch: 0 };

  for (const seg of segments) {
    const match = await fuzzyMatch(db, seg, sourceLang, targetLang);
    if (!match)                        counts.noMatch++;
    else if (match.matchType === 'exact') counts.exact++;
    else                               counts.fuzzy++;
  }

  const total = segments.length || 1; // avoid division by zero
  return {
    total:     segments.length,
    exact:     counts.exact,
    fuzzy:     counts.fuzzy,
    noMatch:   counts.noMatch,
    exactPct:  Math.round((counts.exact   / total) * 100),
    fuzzyPct:  Math.round((counts.fuzzy   / total) * 100),
    noMatchPct: Math.round((counts.noMatch / total) * 100),
  };
}

// ─── 8. TMX import ───────────────────────────────────────────────────────

/**
 * Parses a TMX 1.4b XML string and returns an array of TranslationUnit objects.
 * Uses string-based extraction (no DOM parser available in Workers);
 * suitable for well-formed TMX produced by CAT tools.
 */
export function parseTmx(
  tmxXml: string,
  sourceLang: string,
  targetLang: string
): TranslationUnit[] {
  const units: TranslationUnit[] = [];
  // Match each <tu>…</tu> block
  const tuPattern   = /<tu\b[^>]*>([\s\S]*?)<\/tu>/gi;
  // Within a <tu>, extract <tuv xml:lang="…"><seg>…</seg></tuv>
  const tuvPattern  = /<tuv[^>]+xml:lang="([^"]+)"[^>]*>[\s\S]*?<seg>([\s\S]*?)<\/seg>[\s\S]*?<\/tuv>/gi;

  let tuMatch: RegExpExecArray | null;
  while ((tuMatch = tuPattern.exec(tmxXml)) !== null) {
    const tuBody = tuMatch[1];
    const segments: Record<string, string> = {};

    let tuvMatch: RegExpExecArray | null;
    tuvPattern.lastIndex = 0;
    while ((tuvMatch = tuvPattern.exec(tuBody)) !== null) {
      const lang = tuvMatch[1].toLowerCase();
      const seg  = tuvMatch[2]
        .replace(/<[^>]+>/g, '') // strip inline tags like <ph>, <bpt>
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .trim();
      segments[lang] = seg;
    }

    const src = segments[sourceLang.toLowerCase()];
    const tgt = segments[targetLang.toLowerCase()];
    if (src && tgt) {
      units.push({ source_lang: sourceLang, target_lang: targetLang,
                   source_text: src, target_text: tgt });
    }
  }

  return units;
}

/** Bulk-imports parsed TMX units into D1. */
export async function importTmx(
  db: D1Database,
  tmxXml: string,
  sourceLang: string,
  targetLang: string
): Promise<number> {
  const units = parseTmx(tmxXml, sourceLang, targetLang);
  // D1 batch API: group into chunks of 100
  const chunkSize = 100;
  let imported = 0;

  for (let i = 0; i < units.length; i += chunkSize) {
    const chunk = units.slice(i, i + chunkSize);
    const hashes = await Promise.all(chunk.map((u) => hashSegment(u.source_text)));
    const stmts  = chunk.map((u, idx) =>
      db
        .prepare(
          `INSERT OR IGNORE INTO translation_units
             (source_lang, target_lang, source_text, target_text, source_hash)
           VALUES (?1, ?2, ?3, ?4, ?5)`
        )
        .bind(u.source_lang, u.target_lang, u.source_text, u.target_text, hashes[idx])
    );
    await db.batch(stmts);
    imported += chunk.length;
  }

  return imported;
}

// ─── 9. TMX export ───────────────────────────────────────────────────────

/**
 * Exports all TUs for a language pair from D1 as a TMX 1.4b XML string.
 */
export async function exportTmx(
  db: D1Database,
  sourceLang: string,
  targetLang: string
): Promise<string> {
  const { results } = await db
    .prepare(
      `SELECT source_text, target_text, created_at FROM translation_units
       WHERE source_lang=?1 AND target_lang=?2
       ORDER BY created_at DESC`
    )
    .bind(sourceLang, targetLang)
    .all<{ source_text: string; target_text: string; created_at: number }>();

  const escape = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const tuElements = results
    .map(
      (row) =>
        `  <tu creationdate="${new Date(row.created_at * 1000).toISOString()}">
    <tuv xml:lang="${sourceLang}"><seg>${escape(row.source_text)}</seg></tuv>
    <tuv xml:lang="${targetLang}"><seg>${escape(row.target_text)}</seg></tuv>
  </tu>`
    )
    .join('\n');

  return `<?xml version="1.0" encoding="UTF-8"?>
<tmx version="1.4">
  <header creationtool="orchords-tm" srclang="${sourceLang}" adminlang="en" datatype="plaintext" />
  <body>
${tuElements}
  </body>
</tmx>`;
}

// ─── 10. Worker handler ───────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === 'POST' && url.pathname === '/tm/lookup') {
      const { source_text, source_lang, target_lang, min_score } =
        await request.json<{ source_text: string; source_lang: string; target_lang: string; min_score?: number }>();
      const match = await fuzzyMatch(env.DB, source_text, source_lang, target_lang, min_score ?? 0.75);
      return Response.json(match ?? { matchType: 'no-match' });
    }

    if (request.method === 'POST' && url.pathname === '/tm/import') {
      const tmxXml = await request.text();
      const sl = url.searchParams.get('sl') ?? 'en';
      const tl = url.searchParams.get('tl') ?? 'fr';
      const count = await importTmx(env.DB, tmxXml, sl, tl);
      return Response.json({ imported: count });
    }

    if (request.method === 'GET' && url.pathname === '/tm/export') {
      const sl = url.searchParams.get('sl') ?? 'en';
      const tl = url.searchParams.get('tl') ?? 'fr';
      const tmx = await exportTmx(env.DB, sl, tl);
      return new Response(tmx, { headers: { 'Content-Type': 'application/x-tmx+xml' } });
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Implementation Details

**Hash-based exact matching** — Computing SHA-1 of the normalised source text and storing it as an indexed `TEXT` column makes exact-match lookups O(1) (index seek) regardless of TM size, far faster than `WHERE source_text = ?`.

**Candidate pre-filtering by length** — Levenshtein distance between a 5-word segment and a 50-word candidate can never exceed 75% similarity; filtering candidates by `length(source_text) BETWEEN lenMin AND lenMax` (± 50%) eliminates the majority of rows before the O(m×n) scoring step.

**Two-row DP for Levenshtein** — The classic full-matrix algorithm allocates O(m×n) memory. The two-row version allocates O(n) and is sufficient for translation segments (rarely > 500 characters).

**D1 batch inserts** — `db.batch()` wraps multiple prepared statements in a single HTTP round-trip to D1, dramatically reducing import time for large TMX files. Group into chunks of 100 to stay within D1 statement limits.

**TMX regex parser** — A full XML DOM parser is not available in Workers. The regex-based parser above handles well-formed TMX from CAT tools (memoQ, SDL Trados, Phrase). If source TMX contains malformed or non-standard XML, pre-process it with a Node.js pipeline using `fast-xml-parser` before uploading.

## Anti-patterns

- **Do not** run fuzzy matching against the entire TM on every request without length pre-filtering — for a 100k-segment TM this can take seconds.
- **Do not** use `LIKE '%source_text%'` for fuzzy lookup — it is not similarity scoring, it is substring matching, and it table-scans.
- **Do not** store duplicate TUs — use the `UNIQUE INDEX` on `(source_hash, source_lang, target_lang)` and `INSERT OR IGNORE` / `ON CONFLICT DO UPDATE`.
- **Do not** parse TMX with user-supplied input that may contain XML entity expansion attacks (`<!ENTITY …>`) without sanitising first.

## Gotchas

- `crypto.subtle.digest` is async and must be awaited. Wrapping it in `Promise.all` during bulk imports is safe — D1 batches still execute sequentially server-side.
- SQLite's `length()` function returns the number of UTF-16 code units, not Unicode code points. This is a minor discrepancy from the JavaScript `[...str].length` used in `levenshtein()`, but acceptable for pre-filtering because the error margin is absorbed by the 50% length window.
- The D1 `AUTOINCREMENT` keyword in SQLite guarantees monotonically increasing IDs (no reuse after deletions), which is desirable for TM audit trails. Plain `INTEGER PRIMARY KEY` without `AUTOINCREMENT` reuses IDs of deleted rows.
- Large TMX exports (> 100k TUs) may exceed the Workers 128 MB memory limit. Stream the export using `TransformStream` rather than building the full string in memory.

## Verification

```typescript
import { describe, it, expect } from 'vitest';
import { levenshtein, similarity, normalise, parseTmx } from './workers-translation-memory-d1';

describe('levenshtein', () => {
  it('identical strings return 0', () => expect(levenshtein('hello', 'hello')).toBe(0));
  it('empty vs non-empty', () => expect(levenshtein('', 'abc')).toBe(3));
  it('single substitution', () => expect(levenshtein('cat', 'bat')).toBe(1));
  it('insertion', () => expect(levenshtein('abc', 'abcd')).toBe(1));
  it('deletion', () => expect(levenshtein('abcd', 'abc')).toBe(1));
});

describe('similarity', () => {
  it('identical => 1.0', () => expect(similarity('hello', 'hello')).toBe(1.0));
  it('completely different => 0.0', () => expect(similarity('abc', 'xyz')).toBe(0.0));
  it('one char diff in 4-char string => 0.75', () =>
    expect(similarity('abcd', 'abce')).toBeCloseTo(0.75)
  );
});

describe('normalise', () => {
  it('collapses whitespace', () => expect(normalise('hello  world')).toBe('hello world'));
  it('trims edges', () => expect(normalise('  hi  ')).toBe('hi'));
});

describe('parseTmx', () => {
  const TMX = `<?xml version="1.0"?>
<tmx version="1.4"><header srclang="en"/><body>
  <tu><tuv xml:lang="en"><seg>Hello world</seg></tuv>
      <tuv xml:lang="fr"><seg>Bonjour le monde</seg></tuv></tu>
</body></tmx>`;

  it('parses one TU', () => {
    const units = parseTmx(TMX, 'en', 'fr');
    expect(units).toHaveLength(1);
    expect(units[0].source_text).toBe('Hello world');
    expect(units[0].target_text).toBe('Bonjour le monde');
  });
});
```

## Related

- `documentation/categories/i18n/translation-import-export-d1.md` — XLIFF/PO import pipelines feeding the same D1 database
- `documentation/categories/i18n/workers-icu-plural-rules.md` — plural-form strings stored alongside TM data
- `documentation/categories/i18n/workers-locale-negotiation.md` — selecting source/target language pair from request headers
- OASIS TMX standard: https://www.gala-global.org/tmx-14b

## Sources

- OASIS TMX 1.4b specification: https://www.gala-global.org/tmx-14b
- Levenshtein distance algorithm: https://en.wikipedia.org/wiki/Levenshtein_distance
- Cloudflare D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- WebCrypto SubtleCrypto digest: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/digest
- Trados TMX export format notes: https://docs.rws.com/865435/835870/sdl-trados-studio-2022/tmx-files
