# mongodb-aggregation-pipeline

**Issue:** Complex MongoDB queries written as application code instead of using the aggregation pipeline
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Fetching thousands of documents and filtering/grouping in application memory. Report queries timing out.

## Pattern / Solution
Aggregation pipeline stages:  (filter early, uses indexes),  (aggregate),  (reshape),  (join),  (flatten arrays), , . Always put  first to reduce documents in pipeline.

## Gotchas
- Pipeline stages process documents sequentially -- order matters for performance
-  loads the entire foreign collection into memory if no index on localField/foreignField
-  cannot use an index and requires a full scan if  does not reduce dataset first

## Related
- mongodb-schema-design
- mongodb-indexing-patterns
- cte-common-table-expressions
