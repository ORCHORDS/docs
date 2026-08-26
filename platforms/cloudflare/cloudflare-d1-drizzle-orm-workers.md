# D1 with Drizzle ORM in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You want type-safe SQL queries against Cloudflare D1 using Drizzle ORM — including schema definitions, migration generation via `drizzle-kit`, and transactional patterns — without a separate migration server.

## Context
Drizzle ORM supports Cloudflare D1 via the `drizzle-orm/d1` adapter. Schema definitions live as TypeScript files; `drizzle-kit generate` emits plain SQL migration files that `wrangler d1 migrations apply` runs. This keeps migrations in the same repo as your Worker, usable both locally and in CI. Drizzle's query builder is type-checked at compile time against your schema — a broken column reference is a TypeScript error, not a runtime crash. D1's synchronous binding (`env.DB`) is wrapped by Drizzle into a promise-based interface compatible with Workers' async model.

## Setup

Install dependencies:
```bash
npm install drizzle-orm
npm install --save-dev drizzle-kit @cloudflare/workers-types
```

`wrangler.toml`:
```toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[[d1_databases]]
binding = "DB"
database_name = "my-database"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
migrations_dir = "drizzle/migrations"
```

`drizzle.config.ts` (for drizzle-kit CLI):
```typescript
import type { Config } from "drizzle-kit";

export default {
  schema: "./src/schema.ts",
  out: "./drizzle/migrations",
  driver: "d1-http",
  dbCredentials: {
    accountId: process.env.CLOUDFLARE_ACCOUNT_ID!,
    databaseId: process.env.CLOUDFLARE_D1_DATABASE_ID!,
    token: process.env.CLOUDFLARE_API_TOKEN!,
  },
} satisfies Config;
```

## Schema Definition

`src/schema.ts`:
```typescript
import { sqliteTable, text, integer, real, index } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";

export const users = sqliteTable(
  "users",
  {
    id: text("id").primaryKey(), // ULID or UUID
    email: text("email").notNull().unique(),
    displayName: text("display_name").notNull(),
    createdAt: integer("created_at", { mode: "timestamp" })
      .notNull()
      .default(sql`(unixepoch())`),
    plan: text("plan", { enum: ["free", "pro", "enterprise"] })
      .notNull()
      .default("free"),
  },
  (t) => ({
    emailIdx: index("users_email_idx").on(t.email),
  })
);

export const posts = sqliteTable(
  "posts",
  {
    id: text("id").primaryKey(),
    userId: text("user_id")
      .notNull()
      .references(() => users.id, { onDelete: "cascade" }),
    title: text("title").notNull(),
    body: text("body").notNull(),
    publishedAt: integer("published_at", { mode: "timestamp" }),
    viewCount: integer("view_count").notNull().default(0),
    score: real("score"),
  },
  (t) => ({
    userIdx: index("posts_user_idx").on(t.userId),
    publishedIdx: index("posts_published_idx").on(t.publishedAt),
  })
);

// Inferred TypeScript types
export type User = typeof users.$inferSelect;
export type NewUser = typeof users.$inferInsert;
export type Post = typeof posts.$inferSelect;
export type NewPost = typeof posts.$inferInsert;
```

## Query Patterns in Workers

`src/db.ts` — instantiate Drizzle per request:
```typescript
import { drizzle } from "drizzle-orm/d1";
import * as schema from "./schema";

export function getDb(d1: D1Database) {
  return drizzle(d1, { schema });
}
```

`src/index.ts` — typical CRUD + join patterns:
```typescript
import { eq, desc, and, isNotNull, gt } from "drizzle-orm";
import { getDb } from "./db";
import { users, posts, type NewUser } from "./schema";

interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const db = getDb(env.DB);
    const url = new URL(request.url);

    // SELECT with filter
    if (url.pathname === "/users") {
      const all = await db
        .select({ id: users.id, email: users.email, plan: users.plan })
        .from(users)
        .where(eq(users.plan, "pro"))
        .orderBy(desc(users.createdAt))
        .limit(20);
      return Response.json(all);
    }

    // INSERT
    if (url.pathname === "/users" && request.method === "POST") {
      const body = await request.json<NewUser>();
      const [inserted] = await db.insert(users).values(body).returning();
      return Response.json(inserted, { status: 201 });
    }

    // JOIN — published posts with author email
    if (url.pathname === "/feed") {
      const feed = await db
        .select({
          postId: posts.id,
          title: posts.title,
          authorEmail: users.email,
          publishedAt: posts.publishedAt,
        })
        .from(posts)
        .innerJoin(users, eq(posts.userId, users.id))
        .where(and(isNotNull(posts.publishedAt), gt(posts.viewCount, 0)))
        .orderBy(desc(posts.publishedAt))
        .limit(50);
      return Response.json(feed);
    }

    return new Response("Not found", { status: 404 });
  },
};
```

## Transactions

Drizzle wraps D1's batch API for multi-statement transactions:
```typescript
import { getDb } from "./db";
import { users, posts } from "./schema";

async function createUserWithPost(
  db1: D1Database,
  userId: string,
  email: string,
  postId: string,
  title: string
): Promise<void> {
  const db = getDb(db1);

  await db.transaction(async (tx) => {
    await tx.insert(users).values({
      id: userId,
      email,
      displayName: email.split("@")[0],
    });
    await tx.insert(posts).values({
      id: postId,
      userId,
      title,
      body: "",
    });
    // If either insert throws, both roll back
  });
}
```

## Migrations Workflow

```bash
# Generate SQL migration from schema changes
npx drizzle-kit generate --name add-score-column

# Apply locally (wrangler dev)
wrangler d1 migrations apply my-database --local

# Apply to remote D1
wrangler d1 migrations apply my-database --remote

# Inspect current migration state
wrangler d1 execute my-database --command "SELECT * FROM d1_migrations" --remote
```

## Anti-patterns
- **Instantiating `drizzle()` at module scope** — D1 bindings are request-scoped; instantiate inside the `fetch` handler or use a lazy singleton that takes `env.DB`.
- **Using Drizzle's `push` command against D1** — `drizzle-kit push` does not use wrangler migrations; use `generate` + `wrangler d1 migrations apply` to keep migration history in D1's built-in migration table.
- **Importing all schema files in every query file** — create a central `schema.ts` barrel file and import from it; Drizzle needs the full schema to resolve foreign-key relations in query mode.
- **Relying on `db.query.*` (relational API) without passing `schema` to `drizzle()`** — the relational query builder requires the schema object at instantiation time.
- **Large `IN (...)` lists built with Drizzle's `inArray`** — D1 has a variable limit per statement; chunk arrays over 999 elements.

## Gotchas
- Drizzle's D1 adapter uses the `d1-http` driver for drizzle-kit CLI (remote access via REST) and the `d1` runtime adapter for Workers (direct binding). They require separate config paths.
- `mode: "timestamp"` in column definitions stores epoch integers; remember to convert when serialising to JSON — Drizzle returns `Date` objects in JS but stores integers in SQLite.
- Drizzle does not apply foreign key `PRAGMA foreign_keys = ON` automatically with D1; D1 enables foreign keys by default since compatibility date `2024-03-01`, but older databases need the pragma set in migrations.
- The `returning()` clause is not supported in batch statements via `db.batch()`; use individual awaited inserts inside a `transaction()` block instead.

## Verification
```bash
# Confirm Drizzle types compile with tsc
npx tsc --noEmit

# Run a test query against local D1
wrangler d1 execute my-database \
  --command "SELECT name FROM sqlite_master WHERE type='table'" --local

# List applied migrations
wrangler d1 execute my-database \
  --command "SELECT * FROM d1_migrations ORDER BY applied_at DESC" --local
```

## Related
- [d1-best-practices.md](d1-best-practices.md)
- [d1-migration-best-practices.md](d1-migration-best-practices.md)
- [d1-typescript-patterns.md](d1-typescript-patterns.md)
- [d1-transactions-isolation.md](d1-transactions-isolation.md)
- [d1-foreign-keys.md](d1-foreign-keys.md)

## Sources
- https://orm.drizzle.team/docs/get-started/d1-new
- https://orm.drizzle.team/docs/d1
- https://developers.cloudflare.com/d1/reference/migrations/
- https://orm.drizzle.team/kit-docs/overview
