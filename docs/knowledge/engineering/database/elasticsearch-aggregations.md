# elasticsearch-aggregations

**Issue:** Elasticsearch aggregations on high-cardinality fields are memory-intensive
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Terms aggregation on user_id field with millions of unique values causes circuit breaker exceptions. Dashboard queries timing out.

## Pattern / Solution
Bucket aggregations: terms, date_histogram, range. Metric aggregations: avg, sum, min, max, cardinality. For high-cardinality: use sampler aggregation for approximate results, use cardinality aggregation (HyperLogLog) for unique counts. Optimize with filter aggregation to reduce dataset before bucketing.

## Gotchas
- Terms aggregation returns only top N buckets by default -- increase size but memory cost grows
- cardinality aggregation is approximate (HyperLogLog) -- precision controlled by precision_threshold
- Nested aggregations multiply memory usage exponentially

## Related
- elasticsearch-mapping
- elasticsearch-relevance-tuning
- clickhouse-analytics
