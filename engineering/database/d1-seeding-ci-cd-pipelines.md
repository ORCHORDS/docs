# Database Seeding Strategies for D1 in CI/CD Pipelines
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your Vitest or Playwright test suite needs a deterministic, isolated D1 database state before
each run — but seed data applied in one test bleeds into the next, or the local `--local`
D1 file is stale because a migration was added. In CI (GitHub Actions, Workers CI), the
pipeline re-creates the D1 file on every run but you have no repeatable way to load
reference data, so tests assert against empty tables and pass locally but fail in CI.

## Context

Cloudflare D1 has two runtime modes for testing:

| Mode | Persistence | Use-case |
|------|-------------|----------|
| `--local` (wrangler) | SQLite file on disk | Local dev, slow CI |
| `unstable_dev()` miniflare in-process | In-memory per test | Fast unit/integration |
| Remote D1 with `--env preview` | Persistent Cloudflare-hosted | Staging / smoke |

Most CI pipelines use the `--local` mode or `unstable_dev()`. This article covers seed
strategies for both, plus patterns for staging environments where seed data must be applied
against a real remote D1 without polluting production.

---

## Strategy 1 — SQL Seed Files Applied via Wrangler

The simplest approach: maintain versioned SQL seed files alongside migration files and apply
them after migrations using a Makefile target or shell script.

### Directory layout

```
db/
├── migrations/
│   ├── 0001_initial_schema.sql
│   └── 0002_add_users_table.sql
└── seeds/
    ├── 00_reset.sql          ← idempotent reset (truncate or DELETE)
    ├── 01_reference_data.sql ← enums, lookup tables (safe to replay)
    └── 02_test_fixtures.sql  ← user accounts, sample records
```

### `seeds/00_reset.sql`

```sql
-- Idempotent: safe to run multiple times
PRAGMA foreign_keys = OFF;

DELETE FROM order_items;
DELETE FROM orders;
DELETE FROM users;
DELETE FROM categories;

-- Reset SQLite autoincrement sequences if used
DELETE FROM sqlite_sequence WHERE name IN ('users', 'orders', 'order_items');

PRAGMA foreign_keys = ON;
```

### `seeds/01_reference_data.sql`

```sql
INSERT OR IGNORE INTO categories (id, name, slug) VALUES
  ('cat_01', 'Electronics', 'electronics'),
  ('cat_02', 'Books',       'books'),
  ('cat_03', 'Clothing',    'clothing');
```

Using `INSERT OR IGNORE` ensures re-runs do not fail on primary key conflicts.

### `seeds/02_test_fixtures.sql`

```sql
-- Deterministic UUIDs for predictable assertions in tests
INSERT OR REPLACE INTO users (id, email, name, created_at) VALUES
  ('user_test_001', 'alice@example.com', 'Alice Test', 1700000000),
  ('user_test_002', 'bob@example.com',   'Bob Test',   1700000001);

INSERT OR REPLACE INTO orders (id, user_id, total_cents, status) VALUES
  ('ord_test_001', 'user_test_001', 4999, 'pending'),
  ('ord_test_002', 'user_test_002', 1299, 'completed');
```

### Makefile targets

```makefile
# Makefile
DB_NAME := example project-db

.PHONY: db-reset db-seed db-fresh ci-db

db-reset:
    npx wrangler d1 execute $(DB_NAME) --local --file=db/seeds/00_reset.sql

db-seed: db-reset
    npx wrangler d1 execute $(DB_NAME) --local --file=db/seeds/01_reference_data.sql
    npx wrangler d1 execute $(DB_NAME) --local --file=db/seeds/02_test_fixtures.sql

db-fresh:
    npx wrangler d1 migrations apply $(DB_NAME) --local
    $(MAKE) db-seed

ci-db: db-fresh
    echo "Database ready for CI tests"
```

---

## Strategy 2 — TypeScript Seed Script with Worker Bindings

For complex seed scenarios (hashed passwords, UUID generation, cross-table foreign key
ordering), a TypeScript script is more maintainable than raw SQL.

```typescript
// scripts/seed.ts
// Run with: npx tsx scripts/seed.ts

import { createD1Client } from "./db-client";  // wraps wrangler d1 execute
import { hash } from "bcryptjs";

interface SeedUser {
  id: string;
  email: string;
  passwordHash: string;
  role: "admin" | "user";
}

const SEED_USERS: Omit<SeedUser, "passwordHash">[] = [
  { id: "user_test_001", email: "alice@example.com", role: "admin" },
  { id: "user_test_002", email: "bob@example.com",   role: "user"  },
];

async function main() {
  const db = createD1Client({ local: process.env.CI !== "true" });

  // 1. Reset
  await db.exec(`PRAGMA foreign_keys = OFF`);
  for (const table of ["order_items", "orders", "sessions", "users"]) {
    await db.prepare(`DELETE FROM ${table}`).run();
  }
  await db.exec(`PRAGMA foreign_keys = ON`);

  // 2. Insert users with hashed passwords
  for (const u of SEED_USERS) {
    const passwordHash = await hash("test-password-123", 10);
    await db
      .prepare(
        `INSERT OR REPLACE INTO users (id, email, password_hash, role, created_at)
         VALUES (?, ?, ?, ?, ?)`
      )
      .bind(u.id, u.email, passwordHash, u.role, Date.now())
      .run();
  }

  // 3. Reference data from JSON config
  const categories = await import("../db/seeds/categories.json", { assert: { type: "json" } });
  await db.batch(
    categories.default.map((c: { id: string; name: string; slug: string }) =>
      db
        .prepare(`INSERT OR IGNORE INTO categories (id, name, slug) VALUES (?, ?, ?)`)
        .bind(c.id, c.name, c.slug)
    )
  );

  console.log(`Seeded ${SEED_USERS.length} users, ${categories.default.length} categories`);
}

main().catch((e) => { console.error(e); process.exit(1); });
```

---

## Strategy 3 — Per-Test Isolation with `unstable_dev()` and In-Memory D1

For unit/integration tests where full isolation between tests is required without file I/O:

```typescript
// vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    globals: true,
    environment: "miniflare",
    environmentOptions: {
      d1Databases: ["DB"],        // matches wrangler.toml binding name
      d1Persist: false,           // in-memory — reset between test files
    },
  },
});
```

```typescript
// tests/setup.ts — Vitest global setup
import { readFileSync } from "fs";
import { resolve } from "path";

export async function setupDatabase(env: Env): Promise<void> {
  // Apply all migrations
  const migrationDir = resolve(__dirname, "../db/migrations");
  const files = readdirSync(migrationDir).sort();
  for (const file of files) {
    const sql = readFileSync(resolve(migrationDir, file), "utf-8");
    await env.DB.exec(sql);
  }

  // Apply seeds
  const seedFiles = [
    "db/seeds/01_reference_data.sql",
    "db/seeds/02_test_fixtures.sql",
  ];
  for (const f of seedFiles) {
    const sql = readFileSync(resolve(__dirname, "..", f), "utf-8");
    await env.DB.exec(sql);
  }
}
```

```typescript
// tests/orders.test.ts
import { SELF } from "cloudflare:test";
import { setupDatabase } from "./setup";

describe("Orders API", () => {
  let env: Env;

  beforeEach(async () => {
    // env is provided by the miniflare Vitest environment
    env = (globalThis as any).__D1_ENV__;
    await setupDatabase(env);
  });

  it("returns pending orders for user_test_001", async () => {
    const res = await SELF.fetch("http://localhost/orders?userId=user_test_001");
    const data = await res.json<{ orders: unknown[] }>();
    expect(data.orders).toHaveLength(1);
  });
});
```

---

## Strategy 4 — CI/CD GitHub Actions Pipeline

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: "npm"

      - run: npm ci

      # Apply migrations to local D1
      - name: Apply D1 migrations
        run: npx wrangler d1 migrations apply example project-db --local
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}

      # Seed the local D1
      - name: Seed D1
        run: |
          npx wrangler d1 execute example project-db --local --file=db/seeds/01_reference_data.sql
          npx wrangler d1 execute example project-db --local --file=db/seeds/02_test_fixtures.sql

      - name: Run tests
        run: npx vitest run --reporter=verbose
```

### Staging environment seeding (remote D1, preview environment)

```yaml
      - name: Seed staging D1
        if: github.ref == 'refs/heads/main'
        run: |
          npx wrangler d1 execute example project-db \
            --env preview \
            --file=db/seeds/01_reference_data.sql \
            --remote
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
```

Only reference/lookup data (`01_reference_data.sql`) goes to staging. Test fixtures stay
local to avoid polluting the preview environment with fake users.

---

## Anti-patterns

- **Seeding with `INSERT` (no `OR IGNORE` / `OR REPLACE`)**: Re-running seeds fails on
  primary key conflicts. Always use `INSERT OR IGNORE` for idempotent seeds.

- **Hard-coded `AUTO_INCREMENT` IDs**: If seed rows rely on `ROWID` autoincrement values
  (e.g., `1`, `2`, `3`), reset `sqlite_sequence` in the reset script or use text UUIDs
  that are explicit and predictable.

- **Seeding production with test fixtures**: Gate seed scripts behind environment checks.
  A CI pipeline that accidentally points to the production D1 binding will corrupt live data.

- **Large seed files committed to the repo**: Files over a few MB slow git operations.
  Store large seed datasets in R2 and download them during CI setup rather than committing
  them to the repo.

- **Missing `PRAGMA foreign_keys = OFF` during reset**: If you delete from tables that are
  referenced by other tables, FK violations will abort the delete unless foreign keys are
  disabled for the reset transaction.

---

## Gotchas

- **`wrangler d1 execute --file` vs `--command`**: `--file` reads the entire file and
  executes it; `--command` takes a single SQL string on the command line. Multi-statement
  seed files require `--file`.

- **`wrangler d1 migrations apply --local` creates a `.wrangler/` SQLite file**: Its path
  is `.wrangler/state/v3/d1/<database-id>/db.sqlite`. Deleting this file and re-running
  `migrations apply` gives a clean slate without resetting Wrangler state.

- **`D1_PERSIST` in Vitest environment options**: Setting `d1Persist: false` creates a fresh
  in-memory D1 per test *file*, not per test case. For per-test isolation, wrap each test in a
  transaction and roll it back in `afterEach`, or call `setupDatabase` in `beforeEach`.

- **Wrangler version drift**: Seed scripts that use Wrangler CLI features (e.g., `--remote`)
  may behave differently across major Wrangler versions. Pin the Wrangler version in
  `package.json` and `engines` field.

---

## Verification

```bash
# Confirm seed data is present after seeding
npx wrangler d1 execute example project-db --local \
  --command "SELECT COUNT(*) AS cnt FROM users WHERE id LIKE 'user_test_%'"
# Expected: {"cnt": 2}

# Confirm reference data
npx wrangler d1 execute example project-db --local \
  --command "SELECT id, slug FROM categories ORDER BY id"

# Confirm foreign keys are intact after seeding
npx wrangler d1 execute example project-db --local \
  --command "PRAGMA foreign_key_check"
# Expected: empty result set (no violations)
```

---

## Related

- `d1-migrations-wrangler-ci-cd.md` — migration apply workflow and CI integration
- `database-test-fixtures-isolation.md` — general test isolation patterns
- `d1-schema-versioning-wrangler-migrations.md` — migration file naming conventions
- `d1-batch-operations-performance.md` — batch inserts for large seed datasets
- `database-branching-preview.md` — preview environment database management

## Sources

- Cloudflare D1 Local Development: https://developers.cloudflare.com/d1/local-development/
- Wrangler D1 execute CLI: https://developers.cloudflare.com/workers/wrangler/commands/#d1
- Vitest Miniflare environment: https://developers.cloudflare.com/workers/testing/vitest-integration/
- Cloudflare Workers CI/CD: https://developers.cloudflare.com/workers/ci-cd/
