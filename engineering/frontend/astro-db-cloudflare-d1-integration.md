# Astro DB + Cloudflare D1 Integration

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case:** You want to use Astro DB's type-safe ORM (`drizzle`-backed) against a **Cloudflare D1** database instead of Astro's managed LibSQL, enabling edge-local SQL queries inside Astro server endpoints and actions deployed on Cloudflare Pages.

**Context:** Astro DB (shipped in Astro 4.5+) defaults to LibSQL (Turso). When deploying on Cloudflare Pages with `@astrojs/cloudflare`, you swap the backend to D1 by skipping `@astrojs/db` and using `drizzle-orm` + `drizzle-orm/d1` directly, since Astro DB's hosted LibSQL adapter is incompatible with the D1 binding model. The pattern gives you full Drizzle type-safety at the edge.

---

## Project Setup

```bash
npm create astro@latest my-app -- --template minimal
cd my-app
npx astro add cloudflare
npm install drizzle-orm
npm install -D drizzle-kit wrangler
```

```typescript
// astro.config.mts
import { defineConfig } from 'astro/config';
import cloudflare from '@astrojs/cloudflare';

export default defineConfig({
  output: 'server',          // required for D1 binding access
  adapter: cloudflare({
    platformProxy: { enabled: true },   // exposes CF bindings in dev
  }),
});
```

## Wrangler Configuration

```toml
# wrangler.toml
name = "my-astro-app"
compatibility_date = "2025-09-01"
compatibility_flags = ["nodejs_compat"]
pages_build_output_dir = "dist"

[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

## Drizzle Schema

```typescript
// src/db/schema.ts
import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

export const posts = sqliteTable('posts', {
  id:        integer('id').primaryKey({ autoIncrement: true }),
  slug:      text('slug').notNull().unique(),
  title:     text('title').notNull(),
  body:      text('body').notNull(),
  createdAt: integer('created_at', { mode: 'timestamp' })
               .notNull()
               .$defaultFn(() => new Date()),
});

export type Post = typeof posts.$inferSelect;
export type NewPost = typeof posts.$inferInsert;
```

```typescript
// src/db/index.ts
import { drizzle } from 'drizzle-orm/d1';
import * as schema from './schema';

export function getDB(d1: D1Database) {
  return drizzle(d1, { schema });
}
```

## Astro Server Endpoint — Querying D1

```typescript
// src/pages/api/posts/[slug].ts
import type { APIRoute } from 'astro';
import { getDB } from '@/db';
import { posts } from '@/db/schema';
import { eq } from 'drizzle-orm';

export const GET: APIRoute = async ({ params, locals }) => {
  const db = getDB((locals.runtime as any).env.DB as D1Database);
  const slug = params.slug ?? '';

  const post = await db.query.posts.findFirst({
    where: eq(posts.slug, slug),
  });

  if (!post) return new Response('Not Found', { status: 404 });
  return Response.json(post);
};
```

## Astro Actions with D1 Writes

```typescript
// src/actions/index.ts  (Astro Actions — Astro 4.9+)
import { defineAction } from 'astro:actions';
import { z } from 'astro:schema';
import { getDB } from '@/db';
import { posts } from '@/db/schema';

export const server = {
  createPost: defineAction({
    input: z.object({
      slug:  z.string().min(1).max(100),
      title: z.string().min(1).max(200),
      body:  z.string().min(1),
    }),
    handler: async (input, context) => {
      const db = getDB((context.locals.runtime as any).env.DB as D1Database);
      const [post] = await db.insert(posts).values(input).returning();
      return post;
    },
  }),
};
```

```astro
---
// src/pages/new-post.astro
import { actions } from 'astro:actions';
---
<form method="POST" action={actions.createPost}>
  <input name="slug" required />
  <input name="title" required />
  <textarea name="body" required></textarea>
  <button type="submit">Publish</button>
</form>
```

## Drizzle Migrations with D1

```typescript
// drizzle.config.ts
import { defineConfig } from 'drizzle-kit';

export default defineConfig({
  schema: './src/db/schema.ts',
  out:    './migrations',
  driver: 'd1-http',          // use wrangler for local; HTTP for remote
  dbCredentials: {
    accountId:  process.env.CF_ACCOUNT_ID!,
    databaseId: process.env.CF_D1_DATABASE_ID!,
    token:      process.env.CF_API_TOKEN!,
  },
});
```

```bash
# Generate migration SQL
npx drizzle-kit generate

# Apply locally
wrangler d1 migrations apply my-app-db --local

# Apply to remote
wrangler d1 migrations apply my-app-db --remote
```

## Anti-patterns

- **Importing `@astrojs/db`** when targeting D1 — the LibSQL adapter fails inside Cloudflare's V8 isolate; use `drizzle-orm/d1` directly.
- **Instantiating `drizzle()` at module top level** — D1 binding is only available inside request handlers; create the DB instance per-request.
- **Using `output: 'static'`** with D1 — static mode runs at build time with no access to runtime bindings; `output: 'server'` or `'hybrid'` is required.
- **Running raw SQL strings** instead of the Drizzle query builder — loses type-safety and migration tracking.

## Gotchas

- `locals.runtime.env.DB` is injected by `@astrojs/cloudflare`'s `platformProxy`; the type is `D1Database` from `@cloudflare/workers-types`.
- Drizzle D1 adapter uses D1's **batch API** internally for transactions; explicit `db.transaction()` is supported but translates to `db.batch()`.
- D1 has a **25 MB per-database limit** in the free tier and a **10 ms CPU limit** per query; design schema accordingly.
- `drizzle-kit` with `driver: 'd1-http'` requires `CF_ACCOUNT_ID`, `CF_D1_DATABASE_ID`, and `CF_API_TOKEN` env vars for remote migrations.
- Astro Actions are POST-only by default; GET queries should use standard API routes (`src/pages/api/`).

## Verification

```bash
# Start local dev with D1 proxy
wrangler pages dev ./dist --d1=DB

# Or via Astro dev with platformProxy
npx astro dev

# Test the endpoint
curl http://localhost:4321/api/posts/hello-world

# Check D1 rows locally
wrangler d1 execute my-app-db --local \
  --command "SELECT slug, title FROM posts LIMIT 10;"
```

## Related

- `astro-cloudflare-adapter-ssr-hybrid.md`
- `astro-content-collections-r2-integration.md`
- `astro-server-islands-cloudflare.md`
- `sveltekit-form-actions-cloudflare-d1.md`
- `hono-zod-openapi-typesafe-workers-client.md`

## Sources

- Astro Actions docs: https://docs.astro.build/en/guides/actions/
- @astrojs/cloudflare adapter: https://docs.astro.build/en/guides/integrations-guide/cloudflare/
- Drizzle ORM D1: https://orm.drizzle.team/docs/get-started-sqlite#cloudflare-d1
- Cloudflare D1: https://developers.cloudflare.com/d1/
