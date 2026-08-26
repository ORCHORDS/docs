# feature-cookbook-graphql

**Issue:** GraphQL — schema, resolvers, performance
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a REST API. The mobile team needs different
shapes for the same data. They ask for "give me users
with their posts and likes but not the email." You
build a new endpoint. They ask for another. You have
20 endpoints. The team is overwhelmed.

## Root cause
**REST can require many endpoints for different views.**
GraphQL solves this with a single endpoint + flexible
queries.

**Source:** GraphQL docs:
https://graphql.org/

> "GraphQL is a query language for your API, and a
> server-side runtime for executing queries."

## The "schema" pattern

A GraphQL schema defines the types:
```graphql
type User {
  id: ID!
  email: String!
  displayName: String!
  role: Role!
  posts: [Post!]!
  createdAt: String!
}

type Post {
  id: ID!
  title: String!
  body: String!
  author: User!
  createdAt: String!
}

enum Role {
  VIEWER
  ADMIN
  OWNER
}

type Query {
  user(id: ID!): User
  users(limit: Int = 20, offset: Int = 0): [User!]!
}

type Mutation {
  createUser(input: CreateUserInput!): User!
  updateUser(id: ID!, input: UpdateUserInput!): User!
  deleteUser(id: ID!): Boolean!
}
```

The schema is the contract.

## The "resolver" pattern

A resolver implements the schema:
```ts
const resolvers = {
  Query: {
    user: async (parent, args, context) => {
      return context.db.prepare(`SELECT * FROM users WHERE id = ?`).bind(args.id).first();
    },
    users: async (parent, args, context) => {
      return context.db.prepare(
        `SELECT * FROM users LIMIT ? OFFSET ?`
      ).bind(args.limit, args.offset).all();
    },
  },
  Mutation: {
    createUser: async (parent, args, context) => {
      const id = crypto.randomUUID();
      await context.db.prepare(
        `INSERT INTO users (id, email, displayName) VALUES (?, ?, ?)`
      ).bind(id, args.input.email, args.input.displayName).run();
      return { id, ...args.input };
    },
  },
  User: {
    posts: async (parent, args, context) => {
      return context.db.prepare(
        `SELECT * FROM posts WHERE author_id = ?`
      ).bind(parent.id).all();
    },
  },
};
```

The resolver implements the schema.

## The "DataLoader" pattern (N+1 prevention)

For N+1 queries, use DataLoader:
```ts
import DataLoader from 'dataloader';

const userLoader = new DataLoader(async (ids: string[]) => {
  // Batch the queries
  const placeholders = ids.map(() => '?').join(',');
  const users = await db.prepare(
    `SELECT * FROM users WHERE id IN (${placeholders})`
  ).bind(...ids).all();

  // Return in the same order as the input
  return ids.map(id => users.results.find(u => u.id === id));
});

// In the resolver
User: {
  posts: async (parent, args, context) => {
    // Loads all users in one query, then returns the right one
    return context.userLoader.load(parent.id);
  },
},
```

DataLoader batches + caches; N+1 becomes 2 queries.

## The "depth limit" pattern

For deeply nested queries, limit the depth:
```ts
import depthLimit from 'graphql-depth-limit';

const server = new ApolloServer({
  schema,
  validationRules: [depthLimit(5)],  // Max depth 5
});
```

A depth limit prevents abuse.

## The "complexity limit" pattern

For expensive queries, limit the complexity:
```ts
import { createComplexityLimitRule } from 'graphql-validation-complexity';

const server = new ApolloServer({
  schema,
  validationRules: [
    createComplexityLimitRule(1000, {
      scalarCost: 1,
      objectCost: 2,
      listFactor: 10,
    }),
  ],
});
```

A complexity limit prevents expensive queries.

## The "persisted queries" pattern

For known queries, persist them:
```ts
const persistedQueries = {
  'user-profile': `
    query UserProfile($id: ID!) {
      user(id: $id) {
        id
        displayName
        posts { id title }
      }
    }
  `,
};
```

The query is sent by ID; the body is much smaller.

## The "subscriptions" pattern (real-time)

For real-time, use subscriptions:
```graphql
type Subscription {
  messageAdded(roomId: ID!): Message!
}
```

The client subscribes; the server pushes.

## The "auth" pattern

For auth, use a context:
```ts
const server = new ApolloServer({
  schema,
  context: async ({ request }) => {
    const user = await authenticate(request);
    return { user, db: env.DB };
  },
});
```

The context has the user; resolvers can check it.

## The "auth" resolver pattern

For auth in a resolver:
```ts
const resolvers = {
  Mutation: {
    deleteUser: async (parent, args, context) => {
      if (!context.user) throw new Error('Unauthorized');
      if (context.user.role !== 'admin') throw new Error('Forbidden');
      // ... delete
    },
  },
};
```

The resolver checks auth; the schema doesn't.

## The "pagination" pattern

For pagination, use cursor-based:
```graphql
type Query {
  users(first: Int = 20, after: String): UserConnection!
}

type UserConnection {
  edges: [UserEdge!]!
  pageInfo: PageInfo!
}

type UserEdge {
  cursor: String!
  node: User!
}

type PageInfo {
  hasNextPage: Boolean!
  endCursor: String
}
```

The cursor-based pagination is standard.

## The "error" pattern

For errors, use the GraphQL error format:
```json
{
  "errors": [{
    "message": "User not found",
    "extensions": {
      "code": "USER_NOT_FOUND",
      "status": 404
    }
  }],
  "data": null
}
```

The error has a code + status.

## The "caching" pattern

For caching, use persisted queries + CDN:
```ts
const cache = caches.default;
const cached = await cache.match(request);
if (cached) return cached;
```

The GraphQL endpoint is cached at the edge.

## The "N+1" anti-pattern

Without DataLoader:
```ts
// ❌ N+1: 1 query for users + 1 query per user for posts
User: {
  posts: async (parent) => {
    return db.prepare(`SELECT * FROM posts WHERE author_id = ?`).bind(parent.id).all();
  },
},
```

With 100 users, that's 101 queries.

## The "performance" tip

For performance, use persisted queries:
- **Smaller payloads:** ID instead of the query
- **Caching:** The CDN can cache persisted queries
- **Security:** Whitelist of known queries

## The "GraphQL vs REST" choice

| Use case | Use |
|---|---|
| **Mobile app with complex data** | GraphQL |
| **Public API** | REST |
| **Internal services** | GraphQL or REST |
| **CRUD UI** | REST (simpler) |
| **Complex aggregations** | GraphQL |

For most apps, **REST is fine.** Use GraphQL when the
client needs flexible data shapes.

## Verification
- **Test:** Query returns the right data
- **Test:** Mutation updates the DB
- **Test:** Auth is enforced
- **Live:** Latency is monitored
- **Audit:** Annual review of GraphQL schema

## Gotchas
- **The "N+1" anti-pattern.** Use DataLoader.
- **The "no depth limit" anti-pattern.** A query can be
  arbitrarily deep; limit it.
- **The "no complexity limit" anti-pattern.** A query can
  be arbitrarily expensive; limit it.
- **The "no auth" anti-pattern.** Every resolver must
  check auth.
- **The "no rate limit" anti-pattern.** GraphQL allows
  multiple operations in one request; rate limit per
  operation.

## Related
- `api-design-best-practices.md`
- `api-design-anti-patterns.md`
- `api-versioning.md`
- `feature-cookbook.md`
- `caching-strategies-detail.md`
- `pagination-patterns.md`
- GraphQL: https://graphql.org/
- Apollo: https://www.apollographql.com/
- DataLoader: https://github.com/graphql/dataloader
