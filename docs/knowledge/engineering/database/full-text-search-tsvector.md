# full-text-search-tsvector

**Issue:** Implementing full-text search natively in PostgreSQL
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LIKE and ILIKE are slow and don't support stemming, ranking, or multi-language search.

## Pattern / Solution
```sql
-- Add generated tsvector column
ALTER TABLE articles
  ADD COLUMN search_vector TSVECTOR
  GENERATED ALWAYS AS (
    to_tsvector(''english'', coalesce(title, '''') || '' '' || coalesce(body, ''''))
  ) STORED;

-- GIN index on the vector
CREATE INDEX idx_articles_fts ON articles USING GIN (search_vector);

-- Query with ranking
SELECT id, title, ts_rank(search_vector, query) AS rank
FROM articles, to_tsquery(''english'', ''postgres & indexing'') query
WHERE search_vector @@ query
ORDER BY rank DESC;
```

## Gotchas
- `to_tsquery` requires valid query syntax — use `websearch_to_tsquery` for user input
- Stopwords are removed (''the'', ''and'') — users may be surprised
- Does not support fuzzy/typo-tolerant search; consider pg_trgm for that

## Related
- `generated-columns.md`
- `partial-indexes.md`
