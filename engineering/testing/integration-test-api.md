# integration-test-api

**Issue:** Testing HTTP API endpoints with real middleware, routing, and DB
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Unit tests for route handlers miss middleware bugs, authentication failures, and serialization issues.

## Pattern / Solution
```ts
// Using Supertest with Express / Fastify
import request from "supertest";
import { app } from "../app";
import { db } from "../db";

beforeAll(async () => await db.migrate.latest());
afterAll(async () => await db.destroy());
beforeEach(async () => await db("users").truncate());

describe("POST /api/users", () => {
  it("creates user and returns 201", async () => {
    const res = await request(app)
      .post("/api/users")
      .send({ name: "Alice", email: "alice@example.com" })
      .set("Authorization", "Bearer test-token");

    expect(res.status).toBe(201);
    expect(res.body).toMatchObject({ name: "Alice" });
    expect(res.body.id).toBeDefined();
  });

  it("returns 400 for duplicate email", async () => {
    await db("users").insert({ name: "Alice", email: "alice@example.com" });
    const res = await request(app)
      .post("/api/users")
      .send({ name: "Bob", email: "alice@example.com" });
    expect(res.status).toBe(400);
  });
});
```

## Gotchas
- Use `app.listen()` only in production entry — keep app object separate for testing
- Truncate/seed tables in beforeEach, not beforeAll
- Test auth middleware separately from business logic

## Related
- `api-testing-supertest.md`
- `integration-test-database.md`
