# d1-testing-local

**Issue:** Testing Cloudflare D1 SQLite queries locally without deploying
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
D1 is a SQLite-based database in Cloudflare Workers. Local testing requires either a mock or the Miniflare/wrangler local runtime.

## Pattern / Solution
Using Miniflare for realistic D1 testing:
```ts
import { Miniflare } from "miniflare";
import { readFileSync } from "fs";

let mf: Miniflare;
let d1: D1Database;

beforeAll(async () => {
  mf = new Miniflare({
    modules: true,
    script: `export default { fetch: () => new Response("ok") }`,
    d1Databases: ["DB"],
  });
  d1 = await mf.getD1Database("DB");

  // Apply schema
  const schema = readFileSync("schema.sql", "utf8");
  await d1.exec(schema);
});

afterAll(() => mf.dispose());

it("inserts and queries user", async () => {
  await d1.prepare("INSERT INTO users (id, name) VALUES (?, ?)")
    .bind("u1", "Alice")
    .run();

  const user = await d1.prepare("SELECT * FROM users WHERE id = ?")
    .bind("u1")
    .first<{ id: string; name: string }>();

  expect(user?.name).toBe("Alice");
});
```

## Gotchas
- D1 uses SQLite dialect — not compatible with PostgreSQL-specific SQL
- Miniflare v3 requires `workerd` binary in PATH (installed via `wrangler`)
- `d1.exec()` runs raw SQL files — use for schema setup

## Related
- `kv-testing-miniflare.md`
- `test-doubles-cloudflare-workers.md`
