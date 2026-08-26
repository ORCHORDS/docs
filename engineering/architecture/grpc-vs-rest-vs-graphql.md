# grpc-vs-rest-vs-graphql

**Issue:** Protocol choice drives significant performance and ergonomic tradeoffs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams default to REST without analysing traffic patterns, then fight over-fetching or chatty request overhead later.

## Pattern / Solution
REST for external public APIs and CRUD resources. gRPC for high-throughput internal service-to-service calls and when strong typing via Protobuf is valued. GraphQL for product APIs where clients vary significantly in their field needs.

## Gotchas
gRPC requires HTTP/2 end-to-end, which complicates load balancer config. GraphQL N+1 query problems require DataLoader patterns. REST is the lowest friction choice for third-party integrations.

## Related
graphql-schema-design, contract-first-api-design, api-gateway-pattern
