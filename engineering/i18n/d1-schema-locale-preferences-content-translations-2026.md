# D1 Schema for User Locale Preferences and Content Translations

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

An example.com platform stores music catalog content (track titles, artist bios, genre labels)
in English and three additional languages, plus per-user locale preferences (display language,
date format preference, currency override, number style). A naive design puts everything in a
single `users` table with a `locale` column and a sibling JSON blob—leading to unindexed locale
scans, no fallback chain, and content duplication on every row. The platform needs a D1 schema
that supports locale fallback, efficient per-locale queries, and editorial workflows (draft,
review, published states per translation).

## Context

Cloudflare D1 is a SQLite-at-the-edge database. SQLite's collation and JSON support (via
`json_extract`, `json_each`) are available in D1, but full-text search and stored procedures are
not. The schema must work within D1's current constraints:

- No `RETURNING` clause in older D1 versions (use last-insert-rowid workaround)
- Maximum row size: 1 MB (sufficient for all translation content)
- No `ARRAY` type: use junction tables or JSON arrays
- `TEXT` collation defaults to `BINARY` (case-sensitive); use `COLLATE NOCASE` for locale tags
- D1 supports batched queries (`db.batch([...])`) for transactional multi-row writes

BCP 47 locale tags are stored as `TEXT` throughout. All locale comparison uses `LOWER()` or
explicit `COLLATE NOCASE` to prevent `en-US` vs `en-us` mismatches from application code.

## Core Schema

```sql
-- migrations/0001_locale_core.sql

-- ─── User locale preferences ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_locale_preferences (
  user_id           TEXT        NOT NULL,
  -- BCP 47 tag: 'en-US', 'ar-SA', 'fr-FR', etc.
  locale            TEXT        NOT NULL COLLATE NOCASE,
  -- Explicit overrides; NULL means "derive from locale"
  date_style        TEXT        CHECK (date_style IN ('full','long','medium','short')),
  time_style        TEXT        CHECK (time_style IN ('full','long','medium','short')),
  number_style      TEXT        CHECK (number_style IN ('decimal','percent','currency','unit')),
  currency_override TEXT,       -- ISO 4217: 'EUR', 'USD', etc. NULL = locale default
  hour_cycle        TEXT        CHECK (hour_cycle IN ('h11','h12','h23','h24')),
  calendar          TEXT,       -- BCP 47 calendar: 'gregory', 'islamic-umalqura', 'hebrew'
  timezone          TEXT,       -- IANA tz: 'Europe/Paris'; NULL = derive from CF request
  updated_at        INTEGER     NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (user_id)
);

CREATE INDEX IF NOT EXISTS idx_ulp_locale ON user_locale_preferences (locale COLLATE NOCASE);

-- ─── Supported locales registry ─────────────────────────────────────────────
-- Acts as the authoritative list of production-active locales.
-- Workers query this to build the Accept-Language negotiation set.
CREATE TABLE IF NOT EXISTS supported_locales (
  locale            TEXT        NOT NULL COLLATE NOCASE PRIMARY KEY,
  -- BCP 47 tag of the fallback locale; NULL for the default locale
  fallback_locale   TEXT        COLLATE NOCASE REFERENCES supported_locales (locale),
  display_name_en   TEXT        NOT NULL,  -- English label for admin UI
  is_rtl            INTEGER     NOT NULL DEFAULT 0 CHECK (is_rtl IN (0,1)),
  is_active         INTEGER     NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  launched_at       INTEGER                          -- NULL = not yet launched
);

INSERT OR IGNORE INTO supported_locales (locale, fallback_locale, display_name_en, is_rtl)
VALUES
  ('en',    NULL,   'English (default)',   0),
  ('en-US', 'en',   'English (US)',        0),
  ('en-GB', 'en',   'English (UK)',        0),
  ('fr',    'en',   'French',              0),
  ('fr-FR', 'fr',   'French (France)',     0),
  ('ar',    'en',   'Arabic',              1),
  ('ar-SA', 'ar',   'Arabic (Saudi)',      1),
  ('he',    'en',   'Hebrew',              1),
  ('ja',    'en',   'Japanese',            0);
```

## Content Translation Schema

```sql
-- migrations/0002_content_translations.sql

-- ─── Content entity catalog (tracks, artists, genres, playlists) ─────────────
CREATE TABLE IF NOT EXISTS content_entities (
  entity_id         TEXT        NOT NULL PRIMARY KEY,  -- UUID v7
  entity_type       TEXT        NOT NULL,              -- 'track','artist','genre','playlist'
  canonical_locale  TEXT        NOT NULL DEFAULT 'en' COLLATE NOCASE,
  created_at        INTEGER     NOT NULL DEFAULT (unixepoch()),
  updated_at        INTEGER     NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_ce_type ON content_entities (entity_type);

-- ─── Per-locale translation rows ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS content_translations (
  entity_id         TEXT        NOT NULL REFERENCES content_entities (entity_id),
  locale            TEXT        NOT NULL COLLATE NOCASE,
  -- Structured fields; add columns per entity_type as needed
  title             TEXT,
  description       TEXT,
  slug              TEXT,       -- locale-specific URL slug
  -- Editorial workflow state
  status            TEXT        NOT NULL DEFAULT 'draft'
                                CHECK (status IN ('draft','review','published','archived')),
  translator_notes  TEXT,       -- JSON object: {"key": "note about term choice"}
  word_count        INTEGER,    -- set on write by application; drives TM cost estimates
  translated_by     TEXT,       -- user_id of last editor
  reviewed_by       TEXT,       -- user_id of reviewer
  published_at      INTEGER,
  created_at        INTEGER     NOT NULL DEFAULT (unixepoch()),
  updated_at        INTEGER     NOT NULL DEFAULT (unixepoch()),
  PRIMARY KEY (entity_id, locale)
);

CREATE INDEX IF NOT EXISTS idx_ct_locale   ON content_translations (locale COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_ct_status   ON content_translations (status);
CREATE INDEX IF NOT EXISTS idx_ct_pub_at   ON content_translations (published_at DESC)
  WHERE status = 'published';
```

## Locale Fallback Chain Query

The fallback chain walks the `supported_locales.fallback_locale` pointer. In SQLite a recursive
CTE resolves this without application-level loops:

```sql
-- Resolve the preferred locale for a given user request, falling back through
-- the chain until a published translation is found.
-- :entity_id  = the content entity to fetch
-- :locale     = the negotiated BCP 47 tag from Accept-Language

WITH RECURSIVE fallback_chain(locale, depth) AS (
  SELECT LOWER(:locale), 0
  UNION ALL
  SELECT LOWER(sl.fallback_locale), fc.depth + 1
  FROM   fallback_chain fc
  JOIN   supported_locales sl ON LOWER(sl.locale) = fc.locale
  WHERE  sl.fallback_locale IS NOT NULL
    AND  fc.depth < 8  -- guard against circular references
)
SELECT ct.locale, ct.title, ct.description, fc.depth AS fallback_depth
FROM   fallback_chain fc
JOIN   content_translations ct
  ON   LOWER(ct.locale) = fc.locale
  AND  ct.entity_id = :entity_id
  AND  ct.status = 'published'
ORDER  BY fc.depth ASC
LIMIT  1;
```

The `depth < 8` guard prevents runaway recursion if a misconfigured locale creates a cycle.
Application code should also validate the `supported_locales` graph on insert.

## Workers Service Layer

```ts
// src/services/translation-service.ts
import { Env } from '../env';

export interface ContentTranslation {
  locale: string;
  title: string | null;
  description: string | null;
  fallback_depth: number;
}

const FALLBACK_QUERY = `
WITH RECURSIVE fallback_chain(locale, depth) AS (
  SELECT LOWER(?1), 0
  UNION ALL
  SELECT LOWER(sl.fallback_locale), fc.depth + 1
  FROM   fallback_chain fc
  JOIN   supported_locales sl ON LOWER(sl.locale) = fc.locale
  WHERE  sl.fallback_locale IS NOT NULL AND fc.depth < 8
)
SELECT ct.locale, ct.title, ct.description, fc.depth AS fallback_depth
FROM   fallback_chain fc
JOIN   content_translations ct
  ON   LOWER(ct.locale) = fc.locale
  AND  ct.entity_id = ?2
  AND  ct.status = 'published'
ORDER  BY fc.depth ASC LIMIT 1`;

export async function getTranslation(
  db: Env['DB'],
  entityId: string,
  locale: string,
): Promise<ContentTranslation | null> {
  const result = await db
    .prepare(FALLBACK_QUERY)
    .bind(locale, entityId)
    .first<ContentTranslation>();

  return result ?? null;
}

/**
 * Batch-fetch translations for a list of entities (e.g. a playlist page).
 * Avoids N+1 queries by running one prepared statement per locale.
 */
export async function getTranslationBatch(
  db: Env['DB'],
  entityIds: string[],
  locale: string,
): Promise<Map<string, ContentTranslation>> {
  if (entityIds.length === 0) return new Map();

  const placeholders = entityIds.map((_, i) => `?${i + 2}`).join(',');
  const batchQuery = `
    WITH RECURSIVE fallback_chain(locale, depth) AS (
      SELECT LOWER(?1), 0
      UNION ALL
      SELECT LOWER(sl.fallback_locale), fc.depth + 1
      FROM   fallback_chain fc
      JOIN   supported_locales sl ON LOWER(sl.locale) = fc.locale
      WHERE  sl.fallback_locale IS NOT NULL AND fc.depth < 8
    )
    SELECT ct.entity_id, ct.locale, ct.title, ct.description,
           MIN(fc.depth) AS fallback_depth
    FROM   fallback_chain fc
    JOIN   content_translations ct
      ON   LOWER(ct.locale) = fc.locale
      AND  ct.entity_id IN (${placeholders})
      AND  ct.status = 'published'
    GROUP  BY ct.entity_id
    ORDER  BY ct.entity_id, MIN(fc.depth)`;

  const rows = await db
    .prepare(batchQuery)
    .bind(locale, ...entityIds)
    .all<ContentTranslation & { entity_id: string }>();

  const map = new Map<string, ContentTranslation>();
  for (const row of rows.results) {
    if (!map.has(row.entity_id)) map.set(row.entity_id, row);
  }
  return map;
}
```

## User Locale Preference Upsert

```ts
// src/services/user-locale-service.ts
interface LocalePreferences {
  locale: string;
  currency_override?: string;
  hour_cycle?: 'h11' | 'h12' | 'h23' | 'h24';
  timezone?: string;
  calendar?: string;
}

export async function upsertUserLocale(
  db: Env['DB'],
  userId: string,
  prefs: LocalePreferences,
): Promise<void> {
  await db.prepare(`
    INSERT INTO user_locale_preferences
      (user_id, locale, currency_override, hour_cycle, timezone, calendar, updated_at)
    VALUES (?1, LOWER(?2), ?3, ?4, ?5, ?6, unixepoch())
    ON CONFLICT (user_id) DO UPDATE SET
      locale            = excluded.locale,
      currency_override = excluded.currency_override,
      hour_cycle        = excluded.hour_cycle,
      timezone          = excluded.timezone,
      calendar          = excluded.calendar,
      updated_at        = excluded.updated_at
  `).bind(
    userId,
    prefs.locale,
    prefs.currency_override ?? null,
    prefs.hour_cycle ?? null,
    prefs.timezone ?? null,
    prefs.calendar ?? null,
  ).run();
}
```

## Editorial Workflow Query

```sql
-- Translation coverage dashboard: % published per locale
SELECT
  sl.locale,
  sl.display_name_en,
  COUNT(ct.entity_id)                          AS total_entities,
  SUM(CASE WHEN ct.status = 'published' THEN 1 ELSE 0 END) AS published,
  SUM(CASE WHEN ct.status = 'review'    THEN 1 ELSE 0 END) AS in_review,
  SUM(CASE WHEN ct.status = 'draft'     THEN 1 ELSE 0 END) AS in_draft,
  ROUND(
    100.0 * SUM(CASE WHEN ct.status = 'published' THEN 1 ELSE 0 END)
    / MAX(COUNT(ct.entity_id), 1), 1
  ) AS pct_complete
FROM supported_locales sl
LEFT JOIN content_translations ct ON LOWER(ct.locale) = LOWER(sl.locale)
WHERE sl.is_active = 1
GROUP BY sl.locale
ORDER BY pct_complete DESC;
```

## Anti-patterns

- **Storing locale tags as-is without normalizing case.** `'en-US'` and `'en-us'` will not match
  in SQLite's default `BINARY` collation. Always apply `LOWER()` on write or use
  `COLLATE NOCASE` on the column definition (not on ad-hoc comparisons—they bypass indexes).
- **One JSON blob column for all translations.** `json_extract` can retrieve values but the
  column is not indexable per-locale, full-text search is impossible, and editorial workflow
  state (draft/review/published) cannot be queried per locale without parsing JSON in the
  application layer.
- **Hardcoding the fallback chain in application code.** Moving it to the `supported_locales`
  table means locale teams can add new locales and configure their fallback without a code
  deploy.
- **Not indexing `content_translations (locale)`**. Unindexed locale scans on large catalogs
  become full table scans and quickly saturate D1's per-request CPU budget.
- **Fetching user locale preferences on every request without caching.** Wrap the preference
  lookup in KV with a 5-minute TTL: `await env.KV.get('ulp:' + userId)`. The D1 preference row
  changes rarely; paying a D1 read on every request is unnecessary cost and latency.

## Gotchas

- D1's `unixepoch()` returns seconds, not milliseconds. `Date.now()` in Workers returns
  milliseconds. Decide on one epoch unit and be consistent. The schema above uses seconds;
  multiply by 1000 in JS when constructing `new Date(row.updated_at * 1000)`.
- D1 does not support `RETURNING` in all deployment regions as of mid-2026. Use
  `db.prepare('SELECT last_insert_rowid() AS id').first()` after an INSERT if you need the new
  rowid.
- The `WITH RECURSIVE` fallback CTE uses `LOWER()` for case-insensitive joins; this bypasses the
  `COLLATE NOCASE` index on the column. If locale tag lookup becomes a hotspot, add a
  generated column: `locale_lower TEXT GENERATED ALWAYS AS (LOWER(locale)) STORED` and index it.
- BCP 47 subtag granularity: storing `'zh-Hant-TW'` and `'zh-TW'` as separate rows is valid, but
  the fallback chain must be configured explicitly (`'zh-Hant-TW' → 'zh-Hant' → 'zh' → 'en'`).
  The schema supports this but setup is manual.

## Verification

```bash
# Run migrations against a local D1 database
wrangler d1 execute orchords-dev --local --file migrations/0001_locale_core.sql
wrangler d1 execute orchords-dev --local --file migrations/0002_content_translations.sql

# Seed and test fallback chain
wrangler d1 execute orchords-dev --local --command "
  INSERT INTO content_entities VALUES ('ent-001','track','en',unixepoch(),unixepoch());
  INSERT INTO content_translations (entity_id,locale,title,status)
  VALUES ('ent-001','en','Song Title','published');
"

# Request for 'fr-FR' should fall back to 'en' (no French translation seeded)
wrangler d1 execute orchords-dev --local --command "
WITH RECURSIVE fallback_chain(locale,depth) AS (
  SELECT LOWER('fr-FR'),0 UNION ALL
  SELECT LOWER(sl.fallback_locale),fc.depth+1
  FROM fallback_chain fc
  JOIN supported_locales sl ON LOWER(sl.locale)=fc.locale
  WHERE sl.fallback_locale IS NOT NULL AND fc.depth<8
)
SELECT ct.locale,ct.title,fc.depth FROM fallback_chain fc
JOIN content_translations ct ON LOWER(ct.locale)=fc.locale AND ct.entity_id='ent-001'
AND ct.status='published' ORDER BY fc.depth LIMIT 1;
"
# Expected: locale=en, title='Song Title', depth=2 (fr-FR→fr→en)
```

## Related

- `number-system-locale-workers-d1.md`
- `locale-fallback-strategies-2026.md`
- `locale-persistence-cookies-storage-2026.md`
- `content-negotiation-vary-header.md`
- `database-collation-locale-indexing.md`

## Sources

- D1 documentation: https://developers.cloudflare.com/d1/
- SQLite recursive CTEs: https://www.sqlite.org/lang_with.html
- BCP 47 (RFC 5646): https://www.rfc-editor.org/rfc/rfc5646
- CLDR locale fallback data: https://github.com/unicode-org/cldr/blob/main/common/supplemental/parentLocales.xml
- D1 batch API: https://developers.cloudflare.com/d1/worker-api/d1-client-api/#batch-statements
