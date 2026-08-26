# graphql-dataloaders

**Issue:** DataLoader not configured correctly, missing batching benefits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
DataLoader (by Meta) batches multiple calls in a single event loop tick and caches per request. It is the standard solution for N+1 in GraphQL servers.

## Pattern / Solution
1. Create a new DataLoader per request (not global) to avoid stale cache across requests.\n2. Batch function receives array of keys; return results in the same order.\n3. Use loadMany for bulk lookups.\n4. Disable caching for mutations: userLoader.clear(userId) after writes.

## Gotchas
- Results array must be the same length as keys array and in the same order; misalignment causes wrong data.\n- DataLoader cache is per-request-per-loader; don't share loaders across requests.\n- For very large batches, add a maxBatchSize option to prevent overwhelming the database.

## Related
graphql-n-plus-one, n-plus-one-detection, api-response-caching
