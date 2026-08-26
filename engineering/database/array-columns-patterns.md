# array-columns-patterns

**Issue:** Using PostgreSQL array columns for multi-value attributes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tags, labels, and small fixed sets of values can be stored as arrays rather than junction tables.

## Pattern / Solution
```sql
CREATE TABLE articles (
  id   BIGSERIAL PRIMARY KEY,
  tags TEXT[] NOT NULL DEFAULT ''{}''
);

-- GIN index for containment/overlap queries
CREATE INDEX idx_articles_tags ON articles USING GIN (tags);

-- Query: articles containing all given tags
SELECT * FROM articles WHERE tags @> ARRAY[''postgres'', ''indexing''];

-- Query: articles with any of the tags
SELECT * FROM articles WHERE tags && ARRAY[''postgres'', ''redis''];

-- Append a tag
UPDATE articles SET tags = tags || ''{new-tag}'' WHERE id = 1;

-- Remove a tag
UPDATE articles SET tags = array_remove(tags, ''old-tag'') WHERE id = 1;
```

## Gotchas
- Arrays are not portable to MySQL or SQLite
- Large arrays (>100 elements) are better stored in a junction table
- Cannot enforce FK-like constraints on array elements

## Related
- `json-columns-patterns.md`
- `full-text-search-tsvector.md`
