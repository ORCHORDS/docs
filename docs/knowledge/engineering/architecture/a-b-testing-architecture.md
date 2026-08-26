# a-b-testing-architecture

**Issue:** Product decisions are made on intuition rather than measured user behavior
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A redesigned checkout flow ships to all users simultaneously. There is no way to attribute revenue changes to the change.

## Pattern / Solution
Assign users to experiment buckets deterministically using a hash of user ID and experiment key. Serve variants via feature flags. Log exposure events and conversion events to an analytics pipeline. Analyze with statistical significance tests before declaring a winner.

## Gotchas
Novelty effect inflates early results. Run experiments for at least one full business cycle. Avoid running overlapping experiments on the same user population unless interactions are expected to be independent.

## Related
feature-flag-architecture, canary-deployment-architecture, observability-architecture
