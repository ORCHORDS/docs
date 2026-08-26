# mock-server-msw

**Issue:** Mocking HTTP and GraphQL APIs at the network level with Mock Service Worker
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Mocking `fetch` with `jest.mock` breaks when the code uses `axios` or another HTTP client. MSW intercepts at the network level regardless of HTTP library.

## Pattern / Solution
```bash
npm install -D msw
```

`src/mocks/handlers.ts`:
```ts
import { http, HttpResponse, graphql } from "msw";

export const handlers = [
  http.get("/api/users/:id", ({ params }) => {
    return HttpResponse.json({ id: params.id, name: "Alice" });
  }),

  http.post("/api/users", async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({ id: "new-id", ...body }, { status: 201 });
  }),

  graphql.query("GetUser", () =>
    HttpResponse.json({ data: { user: { id: "1", name: "Alice" } } })
  ),
];
```

`src/mocks/server.ts` (Node — for Jest/Vitest):
```ts
import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);
```

`src/test/setup.ts`:
```ts
import { server } from "../mocks/server";
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

## Gotchas
- `onUnhandledRequest: "error"` catches requests missing handlers — preferred
- Override handlers per-test with `server.use(...)` — reset in afterEach
- Browser mode uses Service Worker registration — needs HTTPS or localhost

## Related
- `testing-library-async-patterns.md`
- `wiremock-patterns.md`
