# data-lakehouse-pattern

**Issue:** Data lakes lack ACID transactions while data warehouses are expensive for raw storage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Raw data in S3 cannot be updated or deleted without full partition rewrites, making GDPR compliance and late-arriving corrections painful.

## Pattern / Solution
Add a transactional metadata layer (Delta Lake, Apache Iceberg, Apache Hudi) over object storage. Provides ACID transactions, schema evolution, time travel, and merge/upsert operations on top of cheap storage. Query engines such as Spark and Trino read the table format natively.

## Gotchas
Small file problems emerge with frequent small writes. Use compaction jobs to consolidate files regularly. Table format choice has significant ecosystem implications for tooling compatibility.

## Related
lambda-architecture, kappa-architecture, data-pipeline-architecture
