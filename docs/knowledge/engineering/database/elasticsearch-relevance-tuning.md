# elasticsearch-relevance-tuning

**Issue:** Default Elasticsearch relevance scoring returns unexpected result ordering
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Search results not matching user expectations. Short documents outranking longer relevant ones.

## Pattern / Solution
Relevance is TF-IDF/BM25 by default. Tune with: boost on specific fields; function_score to incorporate business signals; dis_max for best-field queries; multi_match. Phrase matching: match_phrase with slop. Synonyms via custom analyzer token filter. Use explain: true to debug scores.

## Gotchas
- BM25 k1 and b parameters are tunable globally
- Boosting at query time is multiplicative -- normalize boost values to avoid dominance
- search_type: dfs_query_then_fetch for consistent scoring across shards (more network overhead)

## Related
- elasticsearch-mapping
- elasticsearch-aggregations
- full-text-search-tsvector
