# elasticsearch-mapping

**Issue:** Default Elasticsearch dynamic mapping creates too many fields or wrong field types
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Dynamic mapping created thousands of fields from JSON documents, hitting the field count limit. Numeric fields mapped as text preventing range queries.

## Pattern / Solution
Define explicit mappings before indexing. Use keyword for exact-match, faceting, sorting. Use text with appropriate analyzer for full-text search. Disable dynamic mapping: "dynamic": "strict". Multi-field mapping for both search and sort.

## Gotchas
- Mappings are immutable for field types -- changing type requires reindex
- keyword max length is 32766 bytes -- truncated silently; use ignore_above
- Too many fields (>1000) causes mapping explosion

## Related
- elasticsearch-aggregations
- elasticsearch-relevance-tuning
- full-text-search-tsvector
