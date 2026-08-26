# Contract Testing Workers D1 Schema Validation

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

D1 schema migrations on example project / example.com are applied through Wrangler and can drift from the TypeScript types used by Worker query code without triggering a compile-time error. A column rename, a dropped NOT NULL constraint, or a new required column silently breaks runtime queries and surfaces only in production. Contract tests lock the schema at the boundary between migration SQL and application code, catching drift before deployment.

## Context

D1 does not expose a schema introspection API at runtime; instead, `PRAGMA table_info(table_name)` returns column metadata in local SQLite and in the D1 HTTP API. Tests run inside the `@cloudflare/vitest-pool-workers` pool so they have access to the real `D1Database` binding. Schema contracts are expressed as Zod schemas that mirror the expected column list and are validated against `PRAGMA` output in every CI run after migrations are applied.

## Test Setup

Define Zod schemas that represent the expected D1 table shape:

```typescript
// src/db/schema-contracts.ts
import { z } from "zod";

// PRAGMA table_info row shape
const columnInfo = z.object({
  cid: z.number(),
  name: z.string(),
  type: z.string(),
  notnull: z.number(), // 0 | 1
  dflt_value: z.string().nullable(),
  pk: z.number(), // 0 | 1
});

export type ColumnInfo = z.infer<typeof columnInfo>;
export const columnInfoSchema = columnInfo;

export const postsTableContract = z.array(
  z.object({
    name: z.string(),
    type: z.string(),
    notnull: z.number(),
  })
).refine(
  (cols) => {
    const names = cols.map((c) => c.name);
    return (
      names.includes("id") &&
      names.includes("body") &&
      names.includes("author_hash") &&
      names.includes("created_at") &&
      names.includes("deleted_at")
    );
  },
  { message: "posts table is missing required columns" }
);

export const voteCountersTableContract = z.array(
  z.object({ name: z.string(), type: z.string(), notnull: z.number() })
).refine(
  (cols) => {
    const map = Object.fromEntries(cols.map((c) => [c.name, c]));
    return (
      map["post_id"]?.notnull === 1 &&
      map["upvotes"]?.type === "INTEGER" &&
      map["downvotes"]?.type === "INTEGER"
    );
  },
  { message: "vote_counters table contract violated" }
);
```

```typescript
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
      },
    },
  },
});
```

Helper to query PRAGMA and parse with Zod:

```typescript
// src/db/schema-introspect.ts
import { columnInfoSchema, ColumnInfo } from "./schema-contracts";
import { z } from "zod";

export async function getTableColumns(
  db: D1Database,
  tableName: string
): Promise<ColumnInfo[]> {
  const { results } = await db
    .prepare(`PRAGMA table_info(${tableName})`)
    .all<Record<string, unknown>>();

  return z.array(columnInfoSchema).parse(results);
}
```

## Test Cases

```typescript
// src/db/schema-contracts.test.ts
import { env } from "cloudflare:test";
import { describe, it, expect, beforeAll } from "vitest";
import { getTableColumns } from "./schema-introspect";
import {
  postsTableContract,
  voteCountersTableContract,
} from "./schema-contracts";

beforeAll(async () => {
  // Apply all migrations before contract checks
  await env.DB.exec(`
    CREATE TABLE IF NOT EXISTS posts (
      id TEXT PRIMARY KEY,
      body TEXT NOT NULL,
      author_hash TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      deleted_at TEXT
    );
    CREATE TABLE IF NOT EXISTS vote_counters (
      post_id TEXT NOT NULL PRIMARY KEY REFERENCES posts(id),
      upvotes INTEGER NOT NULL DEFAULT 0,
      downvotes INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS comments (
      id TEXT PRIMARY KEY,
      post_id TEXT NOT NULL REFERENCES posts(id),
      body TEXT NOT NULL,
      author_hash TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
  `);
});

describe("D1 schema contracts", () => {
  it("posts table satisfies the required column contract", async () => {
    const cols = await getTableColumns(env.DB, "posts");
    const result = postsTableContract.safeParse(cols);
    expect(result.success, result.error?.message).toBe(true);
  });

  it("vote_counters table satisfies the required column contract", async () => {
    const cols = await getTableColumns(env.DB, "vote_counters");
    const result = voteCountersTableContract.safeParse(cols);
    expect(result.success, result.error?.message).toBe(true);
  });

  it("posts.id is the primary key", async () => {
    const cols = await getTableColumns(env.DB, "posts");
    const idCol = cols.find((c) => c.name === "id");
    expect(idCol?.pk).toBe(1);
  });

  it("posts.body is NOT NULL", async () => {
    const cols = await getTableColumns(env.DB, "posts");
    const bodyCol = cols.find((c) => c.name === "body");
    expect(bodyCol?.notnull).toBe(1);
  });

  it("posts.deleted_at is nullable (soft-delete column)", async () => {
    const cols = await getTableColumns(env.DB, "posts");
    const deletedAt = cols.find((c) => c.name === "deleted_at");
    expect(deletedAt?.notnull).toBe(0);
  });

  it("comments table references posts via post_id", async () => {
    const { results } = await env.DB.prepare(
      "PRAGMA foreign_key_list(comments)"
    ).all<{ table: string; from: string }>();
    expect(results.some((r) => r.table === "posts" && r.from === "post_id")).toBe(
      true
    );
  });

  it("all required tables exist", async () => {
    const { results } = await env.DB.prepare(
      "SELECT name FROM sqlite_master WHERE type='table'"
    ).all<{ name: string }>();
    const tableNames = results.map((r) => r.name);
    expect(tableNames).toContain("posts");
    expect(tableNames).toContain("vote_counters");
    expect(tableNames).toContain("comments");
  });
});
```

## Assertions

Enforce column type contracts explicitly — D1 SQLite accepts any type affinity but application code may assume a specific type:

```typescript
it("vote_counters numeric columns use INTEGER affinity", async () => {
  const cols = await getTableColumns(env.DB, "vote_counters");
  const upvotes = cols.find((c) => c.name === "upvotes");
  const downvotes = cols.find((c) => c.name === "downvotes");

  expect(upvotes?.type).toBe("INTEGER");
  expect(downvotes?.type).toBe("INTEGER");
});

it("posts timestamp columns default to datetime('now')", async () => {
  const cols = await getTableColumns(env.DB, "posts");
  const createdAt = cols.find((c) => c.name === "created_at");
  expect(createdAt?.dflt_value).toBe("(datetime('now'))");
});
```

## CI Integration

Run schema contract tests as the first job so migration errors fail fast before integration tests:

```yaml
# .github/workflows/schema-contract.yml
name: D1 Schema Contract
on: [push, pull_request]

jobs:
  schema-contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - name: Run schema contract tests
        run: pnpm vitest run src/db/schema-contracts.test.ts --reporter=verbose

  integration:
    needs: schema-contract
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pnpm install --frozen-lockfile
      - run: pnpm vitest run src/**/*.test.ts
```

Add a PR comment with the schema diff when a contract test fails:

```yaml
      - name: Post schema failure comment
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '❌ D1 schema contract test failed. Check migration files for column renames or dropped constraints.'
            })
```

## Anti-patterns

- Writing contract tests that only check table existence — column contracts catch the regressions that matter.
- Sharing Zod schemas between the contract test and the query layer — the contract schema must be a separate, deliberately conservative definition.
- Running PRAGMA inside the Worker handler rather than in tests — PRAGMA calls are test-time introspection, not a runtime pattern.
- Using `db.prepare("SELECT * FROM posts LIMIT 0")` to infer columns — column aliases and star expansion hide type information.
- Skipping contract tests when a migration is "trivial" — additive migrations (new nullable columns) can still break NOT NULL assumptions in query helpers.

## Gotchas

- `PRAGMA table_info` returns columns in definition order, not alphabetically — sort before comparing if column order matters.
- D1 in production returns PRAGMA results only in SQL batch or direct query; the local Miniflare engine supports the same syntax.
- SQLite type affinity is flexible: a column declared `TEXT` accepts integers — the PRAGMA type string reflects the declared affinity, not the stored value type.
- `PRAGMA foreign_key_list` returns empty results if `PRAGMA foreign_keys = OFF`; always enable it before running FK contract assertions.
- `dflt_value` in PRAGMA output includes wrapping parentheses for expressions: `datetime('now')` is stored as `(datetime('now'))`.

## Verification

```bash
# Run schema contracts in isolation
pnpm vitest run src/db/schema-contracts.test.ts --reporter=verbose

# Simulate a migration regression by renaming a column, then re-run:
# ALTER TABLE posts RENAME COLUMN body TO content;
# Expect: "posts table is missing required columns" contract failure
```

## Related

- [api-contract-testing-schema-validation.md](api-contract-testing-schema-validation.md)
- [zod-api-contract-testing-vitest.md](zod-api-contract-testing-vitest.md)
- [miniflare-d1-migration-testing.md](miniflare-d1-migration-testing.md)
- [d1-test-fixtures-wrangler-seed.md](d1-test-fixtures-wrangler-seed.md)

## Sources

- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://www.sqlite.org/pragma.html#pragma_table_info
- https://zod.dev/
- https://developers.cloudflare.com/workers/testing/vitest-integration/
