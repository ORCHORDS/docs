# search-system-design

**Issue:** SQL LIKE queries cannot provide relevant full-text search results at scale
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A product catalog search returns irrelevant results and degrades database performance as the catalog grows to millions of items.

## Pattern / Solution
Index documents in a dedicated search engine such as Elasticsearch, OpenSearch, or Solr. Build an indexing pipeline that syncs changes from the primary database. Implement relevance ranking with BM25 or learned models. Add faceted filtering, typo tolerance, and synonyms.

## Gotchas
Search indexes lag behind the primary database. Deleted documents must be explicitly removed. Index size and query latency grow with document count and require tuning sharding accordingly. Partial updates require careful index merge strategies.

## Related
data-pipeline-architecture, cache-aside-pattern, recommendation-system-design
