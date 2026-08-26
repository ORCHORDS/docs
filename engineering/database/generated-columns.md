# generated-columns

**Issue:** Using database-computed columns to keep derived data consistent
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Storing computed values (e.g., full_name = first + last) in regular columns requires triggers or app logic to stay in sync.

## Pattern / Solution
```sql
-- STORED generated column (persisted, indexable)
CREATE TABLE people (
  first_name TEXT NOT NULL,
  last_name  TEXT NOT NULL,
  full_name  TEXT GENERATED ALWAYS AS (first_name || '' '' || last_name) STORED
);

-- Use in full-text search
ALTER TABLE articles
  ADD COLUMN fts TSVECTOR
  GENERATED ALWAYS AS (to_tsvector(''english'', title || '' '' || body)) STORED;

CREATE INDEX idx_articles_fts ON articles USING GIN (fts);
```

## Gotchas
- VIRTUAL (not stored) generated columns are not yet supported in PostgreSQL (as of PG16); only STORED
- Cannot INSERT/UPDATE a generated column directly
- Expression must be immutable (no volatile functions, no subqueries)
- Adds storage cost equal to a regular column

## Related
- `full-text-search-tsvector.md`
- `partial-indexes.md`
