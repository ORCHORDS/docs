# feature-cookbook-graphql-detail

**Issue:** GraphQL — schema, resolvers, performance
**Date:** 2026-08-09
**Status:** documented

## Symptom
The mobile team needs different data shapes. You
build a new REST endpoint for each shape. You have
20 endpoints. The team is overwhelmed.

## Root cause
**REST can require many endpoints for different views.**
GraphQL solves this.

**Source:** GraphQL spec:
https://spec.graphql.org/

## The "GraphQL schema" pattern

For a schema:
```graphql
type User {
  id: ID!
  email: String!
  displayName: String!
  role: Role!
  posts(first: Int = 20, after: String): PostConnection!
  createdAt: String!
}

type Post {
  id: ID!
  title: String!
  body: String!
  author: User!
  publishedAt: String
}

enum Role {
  VIEWER
  ADMIN
  OWNER
}

type PostConnection {
  edges: [PostEdge!]!
  pageInfo: PageInfo!
}

type PostEdge {
  cursor: String!
  node: Post!
}

type PageInfo {
  hasNextPage: Boolean!
  endCursor: String
}

type Query {
  user(id: ID!): User
  users(first: Int = 20, after: String): UserConnection!
}

type Mutation {
  createUser(input: CreateUserInput!): User!
  updateUser(id: ID!, input: UpdateUserInput!): User!
  deleteUser(id: ID!): Boolean!
}
```

The schema is the contract.

## The "resolver" pattern

For a resolver:
```ts
const resolvers = {
  Query: {
    user: async (parent, args, context) => {
      return context.loaders.user.load(args.id);
    },
    users: async (parent, args, context) => {
      return context.db.users.list({ first: args.first, after: args.after });
    },
  },
  Mutation: {
    createUser: async (parent, args, context) => {
      if (!context.user) throw new Error('Unauthorized');
      return context.db.users.create(args.input);
    },
  },
  User: {
    posts: async (parent, args, context) => {
      return context.db.posts.listByAuthor(parent.id, { first: args.first, after: args.after });
    },
  },
};
```

The resolver implements the schema.

## The "DataLoader" pattern

For N+1 prevention:
```ts
import DataLoader from 'dataloader';

const userLoader = new DataLoader(async (ids: string[]) => {
  const placeholders = ids.map(() => '?').join(',');
  const users = await db.prepare(
    `SELECT * FROM users WHERE id IN (${placeholders})`
  ).bind(...ids).all();

  return ids.map(id => users.results.find(u => u.id === id));
});

// In the resolver
User: {
  posts: async (parent, args, context) => {
    // Batched + cached
    return context.loaders.userPosts.load(parent.id);
  },
},
```

DataLoader batches + caches.

## The "depth limit" pattern

For deep queries:
```ts
import depthLimit from 'graphql-depth-limit';

const server = new ApolloServer({
  schema,
  validationRules: [depthLimit(5)],
});
```

The depth is limited.

## The "complexity limit" pattern

For expensive queries:
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

The complexity is limited.

## The "persisted queries" pattern

For known queries:
```ts
const persistedQueries = {
  'user-profile': `
    query UserProfile($id: ID!) {
      user(id: $id) {
        id
        displayName
      }
    }
  `,
};
```

The query is sent by ID.

## The "auth" pattern

For auth in a resolver:
```ts
const resolvers = {
  Mutation: {
    deleteUser: async (parent, args, context) => {
      if (!context.user) throw new Error('Unauthorized');
      if (context.user.role !== 'admin') throw new Error('Forbidden');

      return context.db.users.delete(args.id);
    },
  },
};
```

The auth is checked.

## The "error format" pattern

For errors:
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

## The "field-level auth" pattern

For field-level:
```ts
const resolvers = {
  User: {
    email: async (parent, args, context) => {
      // Only the user themselves or admin can see the email
      if (parent.id !== context.user?.id && context.user?.role !== 'admin') {
        return null;  // Hide
      }
      return parent.email;
    },
  },
};
```

The field is auth'd.

## The "subscription" pattern

For real-time:
```graphql
type Subscription {
  messageAdded(roomId: ID!): Message!
}
```

```ts
const resolvers = {
  Subscription: {
    messageAdded: {
      subscribe: (parent, args, context) => {
        return context.pubsub.asyncIterator(`message:${args.roomId}`);
      },
    },
  },
};
```

The subscription is set up.

## The "pagination" pattern

For cursor-based:
```graphql
type Query {
  users(first: Int = 20, after: String): UserConnection!
}

type UserConnection {
  edges: [UserEdge!]!
  pageInfo: PageInfo!
}
```

The cursor-based pagination is standard.

## The "N+1 anti-pattern"

For N+1, use DataLoader:
```ts
// ❌ N+1
User: {
  posts: async (parent) => {
    return db.posts.listByAuthor(parent.id);
  },
}

// ✅ With DataLoader
User: {
  posts: async (parent, args, context) => {
    return context.loaders.userPosts.load(parent.id);
  },
},
```

DataLoader batches.

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
- **The "no depth limit" anti-pattern.** Limit depth.
- **The "no auth" anti-pattern.** Every resolver checks.

## Related
- `feature-cookbook-graphql.md`
- `api-design-best-practices.md`
- `feature-cookbook-pagination.md`
- GraphQL: https://graphql.org/
- Apollo: https://www.apollographql.com/
- DataLoader: https://github.com/graphql/dataloader
