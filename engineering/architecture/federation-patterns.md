# federation-patterns

**Issue:** Multiple teams cannot independently evolve their GraphQL schemas
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A monolithic GraphQL gateway becomes a deployment bottleneck. Schema changes require coordination across all teams.

## Pattern / Solution
Use Apollo Federation or schema stitching. Each subgraph owns its domain types. The gateway composes them at query time. Teams deploy subgraphs independently. Entities are extended across subgraph boundaries using key directives.

## Gotchas
Cross-subgraph queries add a composition step latency. Circular entity references between subgraphs cause planning loops. Schema composition validation must run in CI before any subgraph deploys.

## Related
graphql-schema-design, service-mesh-patterns, api-gateway-pattern
