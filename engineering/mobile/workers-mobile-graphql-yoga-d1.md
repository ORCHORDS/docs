# GraphQL Yoga on Workers with D1 Resolver

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to expose a GraphQL API from a Cloudflare Worker backed by D1, using GraphQL Yoga for schema-first design, DataLoader to prevent N+1 queries, persisted queries stored in KV to reduce request payload, and Apollo Client on a React Native / Expo mobile app as the consumer.

## Context

- Cloudflare Workers (module format) + D1 + KV
- `graphql-yoga` 5.x — runs natively on the Workers runtime
- `dataloader` 2.x for batching D1 author lookups
- Persisted queries: client sends SHA-256 hash, Worker fetches SDL from KV
- Mobile: React Native with `@apollo/client` 3.x

---

## Workers GraphQL Yoga Setup

```typescript
// workers/src/graphql/schema.ts
import { createSchema } from 'graphql-yoga';

export const typeDefs = /* GraphQL */ `
  type Author {
    id: ID!
    name: String!
  }

  type Post {
    id: ID!
    title: String!
    body: String!
    createdAt: String!
    author: Author!
  }

  type Query {
    posts(limit: Int = 20, offset: Int = 0): [Post!]!
    post(id: ID!): Post
  }

  type Mutation {
    createPost(title: String!, body: String!, authorId: ID!): Post!
    deletePost(id: ID!): Boolean!
  }
`;
```

```typescript
// workers/src/graphql/resolvers.ts
import DataLoader from 'dataloader';
import type { D1Database } from '@cloudflare/workers-types';

interface Author { id: string; name: string; }
interface Post   { id: string; title: string; body: string; created_at: string; author_id: string; }

function createAuthorLoader(db: D1Database) {
  return new DataLoader<string, Author | null>(async (ids) => {
    const placeholders = ids.map(() => '?').join(',');
    const { results } = await db
      .prepare(`SELECT * FROM authors WHERE id IN (${placeholders})`)
      .bind(...ids)
      .all<Author>();
    const map = new Map(results.map((a) => [String(a.id), a]));
    return ids.map((id) => map.get(id) ?? null);
  });
}

export function buildResolvers(db: D1Database) {
  const authorLoader = createAuthorLoader(db);

  return {
    Query: {
      posts: async (_: unknown, { limit = 20, offset = 0 }: { limit: number; offset: number }) => {
        const { results } = await db
          .prepare('SELECT * FROM posts ORDER BY created_at DESC LIMIT ? OFFSET ?')
          .bind(limit, offset)
          .all<Post>();
        return results;
      },
      post: async (_: unknown, { id }: { id: string }) => {
        return db
          .prepare('SELECT * FROM posts WHERE id = ?')
          .bind(id)
          .first<Post>();
      },
    },
    Mutation: {
      createPost: async (
        _: unknown,
        { title, body, authorId }: { title: string; body: string; authorId: string }
      ) => {
        return db
          .prepare(
            'INSERT INTO posts (title, body, author_id, created_at) VALUES (?, ?, ?, datetime()) RETURNING *'
          )
          .bind(title, body, authorId)
          .first<Post>();
      },
      deletePost: async (_: unknown, { id }: { id: string }) => {
        const info = await db
          .prepare('DELETE FROM posts WHERE id = ?')
          .bind(id)
          .run();
        return info.success;
      },
    },
    Post: {
      author: (post: Post) => authorLoader.load(post.author_id),
      createdAt: (post: Post) => post.created_at,
    },
  };
}
```

---

## Persisted Queries via KV

```typescript
// workers/src/graphql/persistedQueries.ts
import type { KVNamespace } from '@cloudflare/workers-types';

// Client sends: { extensions: { persistedQuery: { sha256Hash: "...", version: 1 } } }
// Worker looks up the query body in KV by hash
export async function resolvePersistedQuery(
  kv: KVNamespace,
  hash: string
): Promise<string | null> {
  return kv.get(`pq:${hash}`);
}

// Preload persisted queries (run once at deployment time)
export async function preloadQuery(
  kv: KVNamespace,
  hash: string,
  query: string
): Promise<void> {
  await kv.put(`pq:${hash}`, query, { expirationTtl: 60 * 60 * 24 * 30 }); // 30 days
}
```

---

## Workers Entry Point (Yoga + KV Persisted Queries)

```typescript
// workers/src/index.ts
import { createYoga } from 'graphql-yoga';
import { buildSchema } from 'graphql';
import { typeDefs } from './graphql/schema';
import { buildResolvers } from './graphql/resolvers';
import { resolvePersistedQuery } from './graphql/persistedQueries';

export interface Env {
  DB: D1Database;
  KV: KVNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const yoga = createYoga<Env>({
      schema: {
        typeDefs,
        resolvers: buildResolvers(env.DB),
      },
      plugins: [
        {
          async onParams({ params, setParams }) {
            // Resolve persisted query by hash
            const ext = params.extensions as Record<string, unknown> | undefined;
            const pq = ext?.persistedQuery as { sha256Hash?: string } | undefined;
            if (pq?.sha256Hash && !params.query) {
              const query = await resolvePersistedQuery(env.KV, pq.sha256Hash);
              if (query) setParams({ ...params, query });
            }
          },
        },
      ],
      graphiql: true,
      cors: {
        origin: '*',
        methods: ['GET', 'POST', 'OPTIONS'],
      },
    });

    return yoga.fetch(request, env);
  },
};
```

---

## D1 Schema

```sql
-- migrations/0001_init.sql
CREATE TABLE IF NOT EXISTS authors (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS posts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  title      TEXT    NOT NULL,
  body       TEXT    NOT NULL,
  author_id  INTEGER NOT NULL REFERENCES authors(id),
  created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_posts_created ON posts(created_at DESC);
CREATE INDEX idx_posts_author  ON posts(author_id);
```

---

## Apollo Client in React Native

```typescript
// app/apollo.ts
import { ApolloClient, InMemoryCache, createHttpLink, gql } from '@apollo/client';
import { createPersistedQueryLink } from '@apollo/client/link/persisted-queries';
import { sha256 } from 'crypto-hash';

const persistedQueriesLink = createPersistedQueryLink({ sha256 });
const httpLink = createHttpLink({ uri: process.env.EXPO_PUBLIC_GQL_URL ?? 'http://localhost:8787/graphql' });

export const apolloClient = new ApolloClient({
  link: persistedQueriesLink.concat(httpLink),
  cache: new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          posts: { merge: false }, // Always replace with fresh list
        },
      },
    },
  }),
});

// Queries
export const GET_POSTS = gql`
  query GetPosts($limit: Int, $offset: Int) {
    posts(limit: $limit, offset: $offset) {
      id
      title
      createdAt
      author {
        id
        name
      }
    }
  }
`;

export const CREATE_POST = gql`
  mutation CreatePost(<title>: String!, $body: String!, $authorId: ID!) {
    createPost(title: <title>, body: $body, authorId: $authorId) {
      id
      title
    }
  }
`;
```

```typescript
// app/screens/PostsScreen.tsx
import { useQuery, useMutation } from '@apollo/client';
import { GET_POSTS, CREATE_POST } from '../apollo';
import { FlatList, Text, View } from 'react-native';

export default function PostsScreen() {
  const { data, loading, error, refetch } = useQuery(GET_POSTS, { variables: { limit: 20, offset: 0 } });
  const [createPost] = useMutation(CREATE_POST, { refetchQueries: [GET_POSTS] });

  if (loading) return <View><Text>Loading…</Text></View>;
  if (error)   return <View><Text>Error: {error.message}</Text></View>;

  return (
    <FlatList
      data={data.posts}
      keyExtractor={(p: { id: string }) => p.id}
      renderItem={({ item }: { item: { id: string; title: string; author: { name: string } } }) => (
        <View style={{ padding: 16, borderBottomWidth: 1, borderColor: '#eee' }}>
          <Text style={{ fontWeight: '600' }}>{item.title}</Text>
          <Text style={{ color: '#666' }}>by {item.author.name}</Text>
        </View>
      )}
    />
  );
}
```

---

## Anti-patterns

- Do NOT use `graphql-yoga` with `express` adapter on Workers — it has no Node.js http module; use the native `fetch` adapter.
- Do NOT call `createYoga` inside the request handler — create it once at module scope (or pass `env` via context).
- Do NOT skip DataLoader when resolving `Post.author` — without batching, 20 posts trigger 20 separate D1 queries.
- Do NOT store persisted query bodies in D1 — KV is lower-latency for key-value lookups at the edge.

## Gotchas

- GraphQL Yoga 5 uses `fetch` globals; ensure `compatibility_date >= "2023-03-01"` in `wrangler.toml`.
- DataLoader caches per-request by default — prime cache or clear it between requests to avoid stale D1 reads.
- Apollo's `createPersistedQueryLink` sends the hash first; if KV misses, it falls back to sending the full query — ensure your Worker accepts both.
- `graphiql: true` should be disabled in production to avoid exposing the schema explorer.

---

## Verification

```bash
# Start Workers dev server
npx wrangler dev

# Run a persisted query hash against KV
npx wrangler kv key get "pq:<sha256>" --binding KV --local

# Query via curl
curl -s -X POST http://localhost:8787/graphql \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ posts(limit:5) { id title } }"}' | jq '.data.posts'

# Inspect D1 for N+1 evidence (enable query logging in resolvers)
npx wrangler d1 execute myapp-prod --local --command "SELECT * FROM posts LIMIT 5"
```

---

## Related

- `documentation/categories/mobile/workers-expo-router-api-routes-d1.md`
- `documentation/categories/mobile/workers-ios-swift-async-d1-api.md`
- `documentation/categories/mobile/workers-flutter-riverpod-api-client.md`

## Sources

- https://developers.cloudflare.com/workers/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/kv/
- https://the-guild.dev/graphql/yoga-server/docs/integrations/integration-with-cloudflare-workers
- https://www.apollographql.com/docs/react/api/link/persisted-queries/
- https://github.com/graphql/dataloader
