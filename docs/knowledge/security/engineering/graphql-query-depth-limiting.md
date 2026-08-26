# graphql-query-depth-limiting

**Issue:** Deeply nested GraphQL queries can cause exponential resolver execution, enabling denial of service attacks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GraphQL's recursive type system allows circular references (User → Friends → User → Friends). A malicious query nesting 10 levels deep can trigger millions of database calls, exhausting CPU and memory. This is a GraphQL-specific DoS vector not present in REST APIs.

## Pattern / Solution
```javascript
// graphql-depth-limit package
import depthLimit from 'graphql-depth-limit';
import { createComplexityRule } from 'graphql-query-complexity';

const server = new ApolloServer({
  typeDefs,
  resolvers,
  validationRules: [
    depthLimit(7),  // reject queries deeper than 7 levels
    createComplexityRule({
      maximumComplexity: 1000,
      estimators: [
        fieldExtensionsEstimator(),
        simpleEstimator({ defaultComplexity: 1 }),
      ],
      onComplete: (complexity) => {
        console.log('Query complexity:', complexity);
      },
    }),
  ],
});
```
```javascript
// Strawberry (Python) — built-in depth limiting
import strawberry
from strawberry.extensions import QueryDepthLimiter

schema = strawberry.Schema(
    query=Query,
    extensions=[QueryDepthLimiter(max_depth=7)]
)
```

## Gotchas
- Depth limit alone is insufficient — a wide query (10,000 top-level items) is also a DoS vector. Combine with complexity limiting.
- Persisted queries (only pre-registered query hashes allowed) are the most robust defense — but require more infrastructure.
- Fragments can obfuscate actual depth — ensure the depth counter resolves fragments before measuring.
- Set a query timeout as a safety net even with depth and complexity limits.

## Related
- `graphql-rate-limiting.md`
- `graphql-introspection-disable.md`
- `rate-limiting-2026.md`
