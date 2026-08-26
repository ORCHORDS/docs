# lambda-architecture

**Issue:** Systems need to serve both historical batch queries and low-latency real-time queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An analytics dashboard must show accurate historical trends and near-real-time updates, but a pure batch pipeline has too high latency and a pure stream processor cannot reprocess history efficiently.

## Pattern / Solution
Run parallel batch and speed layers. The batch layer recomputes accurate views over the full dataset on a schedule. The speed layer processes recent data in real time. A serving layer merges both views for queries.

## Gotchas
Maintaining two codepaths for the same logic causes divergence bugs. Lambda architecture has largely been superseded by kappa architecture for most use cases. The merging logic at query time adds complexity.

## Related
kappa-architecture, data-pipeline-architecture, real-time-streaming-architecture
