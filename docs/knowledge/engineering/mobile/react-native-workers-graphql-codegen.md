# React Native Workers GraphQL Codegen

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

A React Native app communicates with a Cloudflare Workers GraphQL API. Without codegen, query
response types are `any`, mutations are hand-typed, and schema drift causes runtime crashes.
Teams want end-to-end type safety: schema defined once in Workers, TypeScript types generated
for the client, and React Query hooks that are fully typed with zero manual interface
declarations.

## Context

The stack: Workers exposes a GraphQL endpoint via `graphql-yoga` or a thin `itty-router`
handler; `@graphql-codegen/cli` generates typed hooks and operation types from the schema;
React Native consumes them via `@tanstack/react-query` + a plain `fetch`-based GraphQL client
(no Apollo, to keep the bundle small). CI regenerates types on schema change so drift is caught
before merge.

---

## 1. Workers GraphQL Endpoint (graphql-yoga)

```typescript
// worker/src/graphql.ts
import { createYoga } from "graphql-yoga";
import { makeExecutableSchema } from "@graphql-tools/schema";

const typeDefs = /* GraphQL */ `
  type Note {
    id: ID!
    title: String!
    body: String
    createdAt: String!
  }

  type Query {
    notes(limit: Int = 20, offset: Int = 0): [Note!]!
    note(id: ID!): Note
  }

  type Mutation {
    createNote(title: String!, body: String): Note!
    deleteNote(id: ID!): Boolean!
  }
`;

function makeResolvers(env: Env) {
  return {
    Query: {
      notes: async (_: unknown, { limit, offset }: { limit: number; offset: number }) => {
        const { results } = await env.DB.prepare(
          "SELECT id, title, body, created_at FROM notes LIMIT ?1 OFFSET ?2"
        ).bind(limit, offset).all();
        return results.map((r: any) => ({ ...r, createdAt: r.created_at }));
      },
      note: async (_: unknown, { id }: { id: string }) => {
        const row = await env.DB.prepare(
          "SELECT id, title, body, created_at FROM notes WHERE id = ?1"
        ).bind(id).first();
        return row ? { ...row, createdAt: (row as any).created_at } : null;
      },
    },
    Mutation: {
      createNote: async (_: unknown, { title, body }: { title: string; body?: string }) => {
        const id = crypto.randomUUID();
        await env.DB.prepare(
          "INSERT INTO notes (id, title, body, created_at) VALUES (?1, ?2, ?3, datetime('now'))"
        ).bind(id, title, body ?? null).run();
        return { id, title, body, createdAt: new Date().toISOString() };
      },
      deleteNote: async (_: unknown, { id }: { id: string }) => {
        const result = await env.DB.prepare("DELETE FROM notes WHERE id = ?1").bind(id).run();
        return (result.meta.changes ?? 0) > 0;
      },
    },
  };
}

export function createGraphQLHandler(env: Env) {
  return createYoga({
    schema: makeExecutableSchema({ typeDefs, resolvers: makeResolvers(env) }),
    graphqlEndpoint: "/graphql",
    fetchAPI: { fetch, Request, Response },
  });
}
```

---

## 2. Codegen Configuration

```yaml
# codegen.yml
schema: https://api.example.com/graphql
documents: src/**/*.graphql
generates:
  src/generated/graphql.ts:
    plugins:
      - typescript
      - typescript-operations
      - typescript-react-query
    config:
      fetcher:
        func: ../lib/graphql-client#fetcher
        isReactHook: false
      reactQueryVersion: 5
      exposeQueryKeys: true
      exposeFetcher: true
      addInfiniteQuery: false
      scalars:
        ID: string
```

---

## 3. Lightweight Fetch-Based GraphQL Client

```typescript
// src/lib/graphql-client.ts
const ENDPOINT = process.env.EXPO_PUBLIC_WORKERS_URL + "/graphql";

export async function fetcher<TData, TVariables>(
  query: string,
  variables?: TVariables
): Promise<TData> {
  const res = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, variables }),
  });

  if (!res.ok) {
    throw new Error(`GraphQL network error: ${res.status}`);
  }

  const json = await res.json<{ data?: TData; errors?: Array<{ message: string }> }>();

  if (json.errors?.length) {
    throw new Error(json.errors.map((e) => e.message).join("; "));
  }

  if (!json.data) throw new Error("No data in GraphQL response");
  return json.data;
}
```

---

## 4. GraphQL Operation Documents

```graphql
# src/queries/notes.graphql
query GetNotes($limit: Int, $offset: Int) {
  notes(limit: $limit, offset: $offset) {
    id
    title
    body
    createdAt
  }
}

query GetNote($id: ID!) {
  note(id: $id) {
    id
    title
    body
    createdAt
  }
}

mutation CreateNote(<title>: String!, $body: String) {
  createNote(title: <title>, body: $body) {
    id
    title
    createdAt
  }
}

mutation DeleteNote($id: ID!) {
  deleteNote(id: $id)
}
```

---

## 5. React Native Component Using Generated Hooks

```tsx
// src/screens/NotesScreen.tsx
import React from "react";
import { FlatList, Text, TouchableOpacity, View, StyleSheet } from "react-native";
import { useQueryClient } from "@tanstack/react-query";
import {
  useGetNotesQuery,
  useCreateNoteMutation,
  useDeleteNoteMutation,
  GetNotesDocument,
} from "../generated/graphql";

export function NotesScreen() {
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useGetNotesQuery({ limit: 20, offset: 0 });

  const createNote = useCreateNoteMutation({
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: useGetNotesQuery.getKey({ limit: 20, offset: 0 }) }),
  });

  const deleteNote = useDeleteNoteMutation({
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: useGetNotesQuery.getKey({ limit: 20, offset: 0 }) }),
  });

  if (isLoading) return <Text style={styles.status}>Loading…</Text>;
  if (error) return <Text style={styles.status}>Error: {String(error)}</Text>;

  return (
    <View style={styles.container}>
      <FlatList
        data={data?.notes ?? []}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <View style={styles.row}>
            <Text style={styles.title}>{item.title}</Text>
            <TouchableOpacity onPress={() => deleteNote.mutate({ id: item.id })}>
              <Text style={styles.delete}>Delete</Text>
            </TouchableOpacity>
          </View>
        )}
      />
      <TouchableOpacity
        style={styles.fab}
        onPress={() => createNote.mutate({ title: "New Note " + Date.now() })}
      >
        <Text style={styles.fabText}>+</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  row: { flexDirection: "row", justifyContent: "space-between", padding: 16 },
  title: { fontSize: 16 },
  delete: { color: "red" },
  status: { padding: 16 },
  fab: {
    position: "absolute", bottom: 24, right: 24,
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: "#007AFF", alignItems: "center", justifyContent: "center",
  },
  fabText: { color: "#fff", fontSize: 28 },
});
```

---

## 6. CI Schema Drift Check

```yaml
# .github/workflows/graphql-codegen.yml
name: GraphQL Codegen Check
on: [pull_request]
jobs:
  codegen:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci
      - name: Start Workers dev server
        run: npx wrangler dev --port 8787 &
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
      - run: sleep 5
      - name: Run codegen against local dev server
        run: npx graphql-codegen --config codegen.yml
        env:
          GRAPHQL_SCHEMA_URL: http://localhost:8787/graphql
      - name: Fail on generated file changes
        run: git diff --exit-code src/generated/graphql.ts
```

---

## Anti-patterns

- **Importing Apollo Client** — Apollo adds ~100 kB to the React Native bundle; the
  `fetch`-based client in section 3 plus React Query is sufficient and tree-shakable.
- **Inlining `gql` template literals at runtime** — codegen removes the need for runtime
  parsing; use `.graphql` files and let codegen produce plain strings.
- **Committing generated files without CI check** — generated files should be committed but
  the CI drift check (section 6) ensures they are regenerated before merge when the schema
  changes.
- **Wrapping every field in `try/catch` in the component** — let `useQuery`'s `error` state
  handle network/GraphQL errors; only add component-level try/catch for UI-specific logic.

## Gotchas

- **graphql-yoga on Workers CPU limits** — each request spawns schema validation; keep
  `typeDefs` outside the fetch handler so the schema is only parsed once per Worker instance.
- **Codegen `fetcher` path is relative to the output file** — the `func` path in `codegen.yml`
  is resolved relative to `generates` output, not `cwd`; double-check the relative import.
- **`invalidateQueries` key must match `useGetNotesQuery.getKey` exactly** — variables must
  be identical objects; abstract the default variables into a shared constant to avoid mismatch.
- **Workers introspection in production** — disable GraphQL introspection (`allowIntrospection: false`
  in graphql-yoga) for production deployments; leave it enabled on `wrangler dev` for codegen.

## Verification

```bash
# Generate types
npx graphql-codegen --config codegen.yml

# Verify generated file exists and has hook exports
grep "useGetNotesQuery" src/generated/graphql.ts

# Type-check the whole project
npx tsc --noEmit

# Run integration test against Workers dev
EXPO_PUBLIC_WORKERS_URL=http://localhost:8787 npx jest src/__tests__/notes.test.ts
```

## Related

- `react-native-workers-hmac-signed-requests.md`
- `react-native-durable-objects-realtime.md`
- `mobile-api-design-patterns.md`
- `mobile-offline-first-sync-cloudflare-queues.md`

## Sources

- https://the-guild.dev/graphql/codegen/docs/getting-started
- https://the-guild.dev/graphql/yoga-server/docs/integrations/integration-with-cloudflare-workers
- https://tanstack.com/query/latest/docs/framework/react/overview
- https://developers.cloudflare.com/workers/
