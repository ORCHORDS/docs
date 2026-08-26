# graphql-n-plus-one

**Issue:** GraphQL resolvers trigger N+1 database queries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GraphQL resolvers are called per field per object. A query returning 100 users where each user resolver independently fetches their posts results in 101 database queries.

## Pattern / Solution
1. Use DataLoader to batch and cache per-request resolver calls.\n2. Use join-monster or Prisma's query batching for automatic N+1 prevention.\n3. Query complexity analysis: reject queries that would trigger excessive resolver calls.\n4. Implement persisted queries to analyze and optimize at query registration time.\n5. Use @defer directive for non-critical fields that would cause N+1.

## Gotchas
- DataLoader batches within a single event loop tick; async operations between loader calls break batching.\n- Nested DataLoaders reduce queries but result set size can explode.\n- Query depth limiting prevents deeply nested queries but also blocks legitimate deep queries.

## Related
graphql-dataloaders, n-plus-one-detection, database-query-performance
