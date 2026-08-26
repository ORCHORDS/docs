# api-testing-supertest

**Issue:** Testing Express/Fastify HTTP APIs with Supertest
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Need to test HTTP routing, middleware chains, request validation, and response serialization without spinning up a real server.

## Pattern / Solution
```bash
npm install -D supertest @types/supertest
```

```ts
import request from "supertest";
import { app } from "../src/app"; // Express app, not started

describe("GET /api/products", () => {
  it("returns paginated products", async () => {
    const res = await request(app)
      .get("/api/products?page=1&limit=10")
      .set("Authorization", "Bearer valid-token")
      .expect(200)
      .expect("Content-Type", /json/);

    expect(res.body.data).toHaveLength(10);
    expect(res.body.total).toBeGreaterThan(0);
    expect(res.body.page).toBe(1);
  });

  it("validates limit parameter", async () => {
    const res = await request(app)
      .get("/api/products?limit=1000")
      .expect(400);
    expect(res.body.error).toMatch(/limit/i);
  });
});
```

For persistent connections (WebSocket, SSE), use `supertest`'s `agent`:
```ts
const agent = request.agent(app);
await agent.post("/login").send({ email, password });
// agent persists cookies across requests
```

## Gotchas
- Do not call `app.listen()` — Supertest handles the port internally
- Close DB connections in `afterAll` to prevent Jest from hanging
- `expect(200)` chaining vs manual `expect(res.status).toBe(200)` — both work

## Related
- `integration-test-api.md`
- `playwright-api-testing.md`
