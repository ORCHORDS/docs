# graphql-testing-patterns

**Issue:** Testing GraphQL resolvers, queries, and mutations effectively
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GraphQL has unique testing challenges: nested resolvers, N+1 queries, schema validation, and variable handling.

## Pattern / Solution
```ts
// Unit test resolvers directly
it("userResolver returns user by id", async () => {
  const mockDb = { users: { findById: jest.fn().mockResolvedValue({ id: "1", name: "Alice" }) } };
  const result = await resolvers.Query.user(null, { id: "1" }, { db: mockDb });
  expect(result.name).toBe("Alice");
});

// Integration test with executeOperation (Apollo Server)
import { ApolloServer } from "@apollo/server";
import { typeDefs, resolvers } from "../schema";

const server = new ApolloServer({ typeDefs, resolvers });
await server.start();

it("fetches user with nested posts", async () => {
  const res = await server.executeOperation({
    query: `query { user(id: "1") { name posts { title } } }`,
  });
  expect(res.body.kind).toBe("single");
  expect(res.body.singleResult.data?.user.name).toBe("Alice");
});
```

Test with MSW for client-side:
```ts
server.use(
  graphql.query("GetUser", () =>
    HttpResponse.json({ data: { user: { id: "1", name: "Alice" } } })
  )
);
```

## Gotchas
- Test N+1 issues separately with DataLoader monitoring
- Use `graphql-tag` (`gql`) for type-safe query strings
- Validate schema changes don't break existing operations

## Related
- `api-testing-supertest.md`
- `mock-server-msw.md`
