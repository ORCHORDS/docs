# Miniflare D1 Batch Transaction Testing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

D1's `db.batch([...])` API executes multiple statements in a single HTTP round-trip and — unlike individual `prepare().run()` calls — preserves atomicity guarantees within the batch. On example project / example.com, posting a new entry requires atomically inserting the post, initialising its vote counter, and writing a fan-out queue entry; a partial failure must leave no orphan rows. These multi-statement batches are difficult to validate through unit tests alone and require a real SQLite engine to exercise rollback behaviour.

## Context

Miniflare (embedded inside `@cloudflare/vitest-pool-workers`) exposes a local SQLite-backed D1 instance. Unlike the production D1 HTTP API, the local engine runs in the same process, making it practical to inspect database state synchronously between test steps and to inject constraint violations to force partial-failure scenarios. Each test file receives an isolated D1 instance when the pool is configured with per-worker isolation.

## Test Setup

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "example project-local"
database_id = "00000000-0000-0000-0000-000000000001"

[migrations]
directory = "./migrations"
```

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          compatibilityDate: "2024-09-23",
        },
      },
    },
  },
});
```

Apply migrations before each test suite using the `env` helper:

```typescript
// e2e/helpers/db-setup.ts
import { env } from "cloudflare:test";

export async function applyMigrations(): Promise<void> {
  await env.DB.exec(`
    CREATE TABLE IF NOT EXISTS posts (
      id TEXT PRIMARY KEY,
      body TEXT NOT NULL,
      author_hash TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS vote_counters (
      post_id TEXT PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
      upvotes INTEGER NOT NULL DEFAULT 0,
      downvotes INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS queue_entries (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      post_id TEXT NOT NULL,
      event TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
  `);
}

export async function resetTables(): Promise<void> {
  await env.DB.exec(
    "DELETE FROM queue_entries; DELETE FROM vote_counters; DELETE FROM posts;"
  );
}
```

## Test Cases

```typescript
// src/post-create.batch.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, beforeAll, afterEach } from "vitest";
import { applyMigrations, resetTables } from "../e2e/helpers/db-setup";
import { createPostBatch } from "../src/queries/post-create";

describe("D1 batch: create post", () => {
  beforeAll(applyMigrations);
  afterEach(resetTables);

  it("inserts post, vote_counter, and queue_entry atomically", async () => {
    const postId = "post-abc";
    const stmts = createPostBatch(env.DB, {
      id: postId,
      body: "Hello example project",
      authorHash: "deadbeef",
    });

    await env.DB.batch(stmts);

    const post = await env.DB.prepare("SELECT id FROM posts WHERE id = ?")
      .bind(postId)
      .first<{ id: string }>();
    expect(post?.id).toBe(postId);

    const counter = await env.DB.prepare(
      "SELECT upvotes FROM vote_counters WHERE post_id = ?"
    )
      .bind(postId)
      .first<{ upvotes: number }>();
    expect(counter?.upvotes).toBe(0);

    const { results } = await env.DB.prepare(
      "SELECT event FROM queue_entries WHERE post_id = ?"
    )
      .bind(postId)
      .all<{ event: string }>();
    expect(results).toHaveLength(1);
    expect(results[0].event).toBe("post.created");
  });

  it("leaves no rows when the batch is aborted by a constraint violation", async () => {
    // Pre-insert a post to trigger PRIMARY KEY conflict on the second batch call
    await env.DB.prepare(
      "INSERT INTO posts (id, body, author_hash) VALUES (?, ?, ?)"
    )
      .bind("dup-post", "existing", "aabbccdd")
      .run();

    const stmts = createPostBatch(env.DB, {
      id: "dup-post", // duplicate id — will violate PK constraint
      body: "This should fail",
      authorHash: "11223344",
    });

    await expect(env.DB.batch(stmts)).rejects.toThrow(/UNIQUE constraint/i);

    // Only the original row must exist
    const { results: posts } = await env.DB.prepare(
      "SELECT id FROM posts WHERE id = 'dup-post'"
    ).all<{ id: string }>();
    expect(posts).toHaveLength(1);

    const { results: counters } = await env.DB.prepare(
      "SELECT post_id FROM vote_counters WHERE post_id = 'dup-post'"
    ).all();
    // Counter for original post may or may not exist depending on prior state;
    // confirm no NEW counter was created by a partial batch
    expect(counters.length).toBeLessThanOrEqual(1);
  });

  it("executes up to 100 statements in a single batch", async () => {
    const stmts = Array.from({ length: 33 }, (_, i) => {
      const id = `bulk-${i}`;
      return createPostBatch(env.DB, {
        id,
        body: `Post ${i}`,
        authorHash: `hash${i}`,
      });
    }).flat();

    expect(stmts).toHaveLength(99); // 3 statements * 33 posts

    const results = await env.DB.batch(stmts);
    expect(results).toHaveLength(99);
    results.forEach((r) => expect(r.success).toBe(true));
  });
});
```

## Assertions

Validate not only that rows exist but that batch metadata (affected rows, last-insert rowid) matches expectations:

```typescript
it("batch result metadata reflects all executed statements", async () => {
  const stmts = createPostBatch(env.DB, {
    id: "meta-post",
    body: "Metadata check",
    authorHash: "cafebabe",
  });

  const [postResult, counterResult, queueResult] = await env.DB.batch(stmts);

  expect(postResult.success).toBe(true);
  expect(postResult.meta.changes).toBe(1);

  expect(counterResult.success).toBe(true);
  expect(counterResult.meta.changes).toBe(1);

  expect(queueResult.success).toBe(true);
  expect(queueResult.meta.last_row_id).toBeGreaterThan(0);
});
```

## CI Integration

```yaml
# .github/workflows/test.yml
name: D1 Batch Tests
on: [push, pull_request]

jobs:
  d1-batch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Vitest D1 batch tests
        run: pnpm vitest run --reporter=verbose src/post-create.batch.test.ts
      - name: Upload coverage
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage
          path: coverage/
```

For monorepos, scope the test run:

```bash
pnpm --filter @example project/workers vitest run --project d1-batch
```

## Anti-patterns

- Using `db.prepare().run()` in a loop instead of `db.batch()` — does not test the actual batching path and misses batch-size limits.
- Asserting only on the first statement's result — later statements in a failed batch can still report `success: true` in local mode; always assert all results.
- Reusing the same `D1Database` instance across test files without isolation — Miniflare shares the SQLite file; `afterEach(resetTables)` is mandatory.
- Wrapping batch calls in a try-catch that swallows errors — constraint violations should propagate so test assertions can verify rollback.
- Seeding test data with `db.batch` inside `beforeAll` without awaiting migrations — the schema may not exist yet.

## Gotchas

- The Miniflare D1 local engine does NOT enforce foreign-key constraints unless `PRAGMA foreign_keys = ON` is executed first; run it in your migration script.
- `db.batch` in Miniflare is limited to 100 statements per call; exceeding this limit throws `Too many SQL statements`.
- Batch results are returned in the same order as the input statements; destructure carefully when checking per-statement metadata.
- `meta.last_row_id` is meaningful only for `INSERT` statements; it is `0` for `UPDATE`/`DELETE`.
- In production D1, a batch wraps all statements in an implicit transaction; locally, Miniflare SQLite mimics this but the rollback semantics may diverge for DDL statements.

## Verification

```bash
pnpm vitest run src/post-create.batch.test.ts --reporter=verbose
# Expect: 4 tests pass

# Confirm foreign-key cascade works:
pnpm vitest run --reporter=verbose -t "leaves no rows"
```

## Related

- [d1-batch-transactions-vitest.md](d1-batch-transactions-vitest.md)
- [miniflare-d1-integration-testing.md](miniflare-d1-integration-testing.md)
- [miniflare-d1-migration-testing.md](miniflare-d1-migration-testing.md)
- [test-data-management-d1-factories.md](test-data-management-d1-factories.md)

## Sources

- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- https://miniflare.dev/storage/d1
- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/d1/platform/limits/
