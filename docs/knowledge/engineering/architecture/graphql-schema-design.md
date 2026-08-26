# graphql-schema-design

**Issue:** Poorly designed GraphQL schemas lead to N+1 queries and leaky domain boundaries
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A single query triggers hundreds of downstream database calls. Schema types bleed internal identifiers into the public contract.

## Pattern / Solution
Use DataLoader for batching resolver calls. Design types around client use cases, not database tables. Apply query depth and complexity limits. Paginate list fields using cursor-based connections.

## Gotchas
Mutations should return the mutated resource so clients can update their cache. Avoid wrapping every field in a nullable just to be safe it forces null checks everywhere.

## Related
grpc-vs-rest-vs-graphql, federation-patterns, api-gateway-pattern
