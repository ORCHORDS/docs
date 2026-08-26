# Drizzle ORM with D1: Schema Definitions, Migrations, and Vitest Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building a Cloudflare Worker that reads and writes to a D1 database and want:
- Type-safe SQL queries through Drizzle ORM (not raw `.prepare()` strings)
- A reproducible migration workflow using `drizzle-kit` instead of hand-written SQL files
- Vitest Workers pool tests that apply the schema to an in-memory D1 before each test suite

## Context

Drizzle ORM has a first-class D1 adapter (`drizzle-orm/d1`) that wraps a `D1Database`
binding and turns Drizzle query builder calls into batched D1 statements. `drizzle-kit`
generates SQL migration files from TypeScript schema definitions via `drizzle-kit generate`.
Those SQL files are then applied with `wrangler d1 migrations apply` in production and with
the D1 `batch` API in Vitest via `@cloudflare/vitest-pool-workers`. The schema TypeScript
file is the single source of truth for both the runtime query layer and the migration SQL.

## 1. Install Dependencies

```bash
pnpm add drizzle-orm
pnpm add -D drizzle-kit @cloudflare/vitest-pool-workers vitest
```

## 2. Schema Definition

```typescript
// src/db/schema.ts
import { sqliteTable, text, integer, index } from 'drizzle-orm/sqlite-core';

export const users = sqliteTable(
  'users',
  {
    id:        integer('id').primaryKey({ autoIncrement: true }),
    email:     text('email').notNull().unique(),
    name:      text('name').notNull(),
    role:      text('role', { enum: ['admin', 'member', 'viewer'] }).notNull().default('member'),
    createdAt: integer('created_at', { mode: 'timestamp' }).notNull(),
  },
  (t) => [index('users_email_idx').on(t.email)],
);

export const posts = sqliteTable('posts', {
  id:        integer('id').primaryKey({ autoIncrement: true }),
  authorId:  integer('author_id').notNull().references(() => users.id, { onDelete: 'cascade' }),
  title:     text('title').notNull(),
  body:      text('body').notNull(),
  published: integer('published', { mode: 'boolean' }).notNull().default(false),
});
```

## 3. drizzle-kit Configuration

```typescript
// drizzle.config.ts
import type { Config } from 'drizzle-kit';

export default {
  schema:    './src/db/schema.ts',
  out:       './drizzle/migrations',
  dialect:   'd1-http',         // generates SQLite-compatible DDL for D1
  dbCredentials: {
    accountId:  process.env.CLOUDFLARE_ACCOUNT_ID!,
    databaseId: process.env.CLOUDFLARE_DATABASE_ID!,
    token:      process.env.CLOUDFLARE_API_TOKEN!,
  },
} satisfies Config;
```

```bash
# Generate migration SQL from schema
pnpm drizzle-kit generate

# Apply to local dev D1
wrangler d1 migrations apply my-db --local

# Apply to production
wrangler d1 migrations apply my-db --remote
```

## 4. Drizzle Client Factory

```typescript
// src/db/client.ts
import { drizzle } from 'drizzle-orm/d1';
import * as schema from './schema';

export type DrizzleD1 = ReturnType<typeof createDb>;

export function createDb(d1: D1Database) {
  return drizzle(d1, { schema, logger: false });
}
```

## 5. Worker Repository Pattern

```typescript
// src/db/users-repo.ts
import { eq } from 'drizzle-orm';
import { users } from './schema';
import type { DrizzleD1 } from './client';

export class UsersRepository {
  constructor(private readonly db: DrizzleD1) {}

  async findByEmail(email: string) {
    return this.db.select().from(users).where(eq(users.email, email)).get();
  }

  async create(data: { email: string; name: string }) {
    const [row] = await this.db
      .insert(users)
      .values({ ...data, createdAt: new Date() })
      .returning({ id: users.id });
    return row;
  }

  async listAdmins() {
    return this.db
      .select({ id: users.id, email: users.email })
      .from(users)
      .where(eq(users.role, 'admin'))
      .all();
  }
}
```

## 6. Vitest Global Setup: Apply Migrations to In-Memory D1

```typescript
// vitest/global-setup.ts  (runs once in Node before the Workers pool starts)
// Not needed here — migration is applied inside the Workers environment below.
```

```typescript
// vitest/fixtures.ts  — shared fixture applied via beforeAll in each test file
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const MIGRATIONS_DIR = join(process.cwd(), 'drizzle/migrations');

export async function applyMigrations(db: D1Database): Promise<void> {
  const sqlFiles = readdirSync(MIGRATIONS_DIR)
    .filter(f => f.endsWith('.sql'))
    .sort(); // drizzle-kit names files with numeric prefix: 0001_..., 0002_...

  for (const file of sqlFiles) {
    const sql = readFileSync(join(MIGRATIONS_DIR, file), 'utf8');
    // D1 batch accepts multiple statements separated by semicolons
    const statements = sql
      .split(';')
      .map(s => s.trim())
      .filter(Boolean);

    await db.batch(statements.map(s => db.prepare(s)));
  }
}
```

```typescript
// src/db/users-repo.test.ts
import { describe, it, expect, beforeAll } from 'vitest';
import { env } from 'cloudflare:test';
import { createDb } from './client';
import { UsersRepository } from './users-repo';
import { applyMigrations } from '../../vitest/fixtures';

describe('UsersRepository', () => {
  let repo: UsersRepository;

  beforeAll(async () => {
    await applyMigrations(env.DB);
    repo = new UsersRepository(createDb(env.DB));
  });

  it('creates a user and retrieves by email', async () => {
    const created = await repo.create({ email: 'alice@example.com', name: 'Alice' });
    expect(created.id).toBeTypeOf('number');

    const found = await repo.findByEmail('alice@example.com');
    expect(found?.name).toBe('Alice');
    expect(found?.role).toBe('member');
  });

  it('returns undefined for unknown email', async () => {
    const result = await repo.findByEmail('nobody@example.com');
    expect(result).toBeUndefined();
  });

  it('listAdmins returns only admin-role users', async () => {
    // Insert directly via drizzle to set role
    const db = createDb(env.DB);
    await db.insert((await import('./schema')).users).values({
      email: 'admin@example.com',
      name: 'Admin',
      role: 'admin',
      createdAt: new Date(),
    });

    const admins = await repo.listAdmins();
    expect(admins.some(u => u.email === 'admin@example.com')).toBe(true);
  });
});
```

## 7. wrangler.toml Test Binding

```toml
# wrangler.toml
[[d1_databases]]
binding     = "DB"
database_name = "my-db"
database_id   = "your-prod-id"

[env.test]
[[env.test.d1_databases]]
binding     = "DB"
database_name = "my-db-test"
database_id   = "local"   # vitest-pool-workers creates an in-memory D1 for "local"
```

```typescript
// vitest.config.ts
import { defineWorkersConfig } from '@cloudflare/vitest-pool-workers/config';

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: './wrangler.toml', environment: 'test' },
      },
    },
  },
});
```

## Anti-patterns

- **Running `wrangler d1 migrations apply --remote` in CI test jobs** — tests should use
  the local in-memory D1, not the production or staging database.
- **Using `db.run(sql\`CREATE TABLE ...\`)` instead of migration files** — inline DDL in
  tests diverges from the schema over time. Always drive from the generated SQL files.
- **Sharing D1 state across `describe` blocks without resetting** — D1 is not rolled back
  between tests automatically. Use `beforeAll` (once per suite) and insert only what each
  suite needs, or `DELETE FROM table` in `afterEach`.
- **Importing `drizzle-orm` in `drizzle.config.ts`** — `drizzle.config.ts` is a Node
  script run by `drizzle-kit`, not bundled by esbuild. Do not import Workers-specific code
  in it; keep it plain Node-compatible TypeScript.

## Gotchas

- `drizzle-orm/d1` uses D1's `batch` method internally for transactions. D1 transactions
  are serialised; concurrent test files that write to the same D1 instance may deadlock in
  remote mode. Use `--pool-size=1` in Vitest or the local in-memory D1.
- `drizzle-kit generate` with `dialect: 'd1-http'` produces `INTEGER` for `boolean` columns
  (0/1) — ensure your TypeScript types use `mode: 'boolean'` in the schema to keep the
  ORM layer consistent.
- The `.get()` method returns `undefined` on no match; the `.first()` D1 raw API returns
  `null`. When mixing Drizzle and raw D1 calls in tests, normalise the null/undefined
  difference.

## Verification

```bash
# Generate migrations from schema, apply locally, verify table list
pnpm drizzle-kit generate
wrangler d1 migrations apply my-db --local
wrangler d1 execute my-db --local --command "SELECT name FROM sqlite_master WHERE type='table'"

# Run Vitest
pnpm vitest run src/db/ --reporter=verbose

# Type-check the schema and client
pnpm tsc --noEmit
```

## Related

- `wrangler-d1-migrations-local-dev-workflow.md`
- `vitest-workers-d1-fixture-factories.md`
- `vitest-global-setup-d1-migration-runner.md`
- `miniflare-d1-test-seeding-fixtures.md`

## Sources

- Drizzle ORM D1 adapter — https://orm.drizzle.team/docs/get-started/d1-new
- drizzle-kit generate — https://orm.drizzle.team/kit-docs/commands#generate
- Cloudflare D1 + Drizzle guide — https://developers.cloudflare.com/d1/tutorials/d1-and-drizzle/
- `@cloudflare/vitest-pool-workers` — https://developers.cloudflare.com/workers/testing/vitest-integration/
