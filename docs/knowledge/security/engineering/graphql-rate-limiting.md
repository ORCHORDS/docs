# graphql-rate-limiting

**Issue:** Standard HTTP rate limiting is insufficient for GraphQL because multiple operations can be batched in a single request
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A REST API rate limit of 100 req/min is straightforward. In GraphQL, a single POST can contain a batch of 50 queries — effectively multiplying the limit by 50. Attackers use query batching and aliases to bypass per-request rate limits.

## Pattern / Solution
```javascript
// Apollo Server — disable query batching or limit batch size
const server = new ApolloServer({
  typeDefs,
  resolvers,
  allowBatchedHttpRequests: false, // disable batching entirely
});

// If batching is needed, limit batch size
app.use('/graphql', (req, res, next) => {
  const body = req.body;
  if (Array.isArray(body) && body.length > 5) {
    return res.status(429).json({ error: 'Batch limit exceeded' });
  }
  next();
});

// Rate limit by complexity units, not requests
const rateLimiter = new RateLimiterRedis({ points: 10000, duration: 60 });
validationRules: [
  createComplexityRule({
    maximumComplexity: 1000,
    onComplete: async (complexity) => {
      await rateLimiter.consume(userId, complexity);
    }
  })
]
```
```javascript
// Alias flooding prevention — limit alias count per query
function maxAliasesRule(maxAliases = 15) {
  return (context) => ({
    Field(node) {
      if (node.alias) aliasCount++;
      if (aliasCount > maxAliases) {
        context.reportError(new GraphQLError(`Too many aliases`));
      }
    }
  });
}
```

## Gotchas
- Alias attacks: `{ a1: user(id:1) { email } a2: user(id:2) { email } ... a100: ... }` — all in one request.
- Complexity-based rate limiting requires accurate field complexity estimates — calibrate with real load testing.
- Persisted queries eliminate ad-hoc complexity attacks by restricting clients to pre-approved queries.
- Introspection queries have high complexity — exclude them from limits or allow separately.

## Related
- `graphql-query-depth-limiting.md`
- `graphql-introspection-disable.md`
- `rate-limiting-2026.md`
