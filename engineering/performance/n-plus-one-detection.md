# n-plus-one-detection

**Issue:** Loading a list triggers N additional queries for each item
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The N+1 problem: fetching 100 users then querying each user's posts individually results in 101 queries instead of 2. Common in ORMs using lazy loading.

## Pattern / Solution
1. Use eager loading / includes in your ORM: User.findAll({ include: Post }).\n2. Use SQL JOINs to fetch related data in one query.\n3. Use DataLoaders (batching + caching) for GraphQL resolvers.\n4. Monitor with query logging in development; count queries per request.\n5. Use APM tools to detect high query count per request in production.

## Gotchas
- Eager loading can cause large result sets; balance N+1 avoidance with result size.\n- Nested eager loading can produce Cartesian product joins.\n- DataLoader batches within a single event loop tick; don't await between DataLoader calls.

## Related
database-query-performance, graphql-n-plus-one, graphql-dataloaders, connection-pool-sizing
