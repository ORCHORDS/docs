# recommendation-system-design

**Issue:** Generic content fails to engage users when personalization is possible
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An e-commerce site shows the same trending products to all users regardless of their browsing history, missing conversion opportunities.

## Pattern / Solution
Separate the pipeline into offline model training, candidate generation, and real-time ranking. Use collaborative filtering or embedding models offline. Serve candidates from a vector search index. Apply business rules and user context as real-time ranking features.

## Gotchas
Cold-start problem for new users requires fallback to popularity-based recommendations. Model staleness degrades personalization quality over time. Define retraining frequency based on data drift metrics. A/B test ranking changes against a holdout group.

## Related
search-system-design, a-b-testing-architecture, real-time-streaming-architecture
