# graphql-introspection-disable

**Issue:** Enabled GraphQL introspection in production exposes the full API schema to attackers for reconnaissance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GraphQL introspection allows clients to query the complete schema — all types, fields, queries, and mutations. In production, this gifts attackers a detailed map of your API surface, including internal fields, administrative mutations, and data relationships that should not be public knowledge.

## Pattern / Solution
```javascript
// Apollo Server — disable introspection in production
const server = new ApolloServer({
  typeDefs,
  resolvers,
  introspection: process.env.NODE_ENV !== 'production',
});

// graphql-yoga
import { createYoga } from 'graphql-yoga';
const yoga = createYoga({
  schema,
  graphiql: false,  // disable IDE in production
  // introspection disabled by default when graphiql is false
});

// Express GraphQL — middleware option
graphqlHTTP({
  schema,
  graphiql: false,
  customValidateFn: (schema, document, rules) => {
    if (process.env.NODE_ENV === 'production') {
      const noIntrospection = require('graphql-disable-introspection');
      return validate(schema, document, [...rules, noIntrospection]);
    }
    return validate(schema, document, rules);
  }
})
```

## Gotchas
- Disabling introspection is security through obscurity — still enforce authorization on every resolver.
- Some API gateways and developer tools need introspection — provide it on an authenticated, non-public endpoint.
- Schema can still be inferred through field guessing even without introspection — rate limit and monitor unusual queries.
- Development and staging environments should have introspection enabled for developer productivity.

## Related
- `graphql-query-depth-limiting.md`
- `graphql-rate-limiting.md`
- `nosql-injection-mongodb.md`
