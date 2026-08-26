# SQL Injection Prevention: D1 and Cloudflare Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Cloudflare D1 queries return unexpected rows when user-supplied values are concatenated into SQL
strings. WAF logs show `sqli` rule triggers on `/api/posts` with payloads like `' OR '1'='1`.
Integration tests pass because test fixtures use safe values, masking the vulnerability. OWASP ZAP
scan reports A03:2021-Injection findings on the example project API.

## Context

example project (example.com) stores anonymous posts, reactions, and user sessions in Cloudflare D1. Workers
act as the API boundary — all SQL must be parameterized before reaching D1. D1 uses a SQLite-
compatible query engine; SQLite's parameter substitution syntax (`?`) applies. There is no ORM by
default in Workers; raw SQL via `db.prepare()` is the idiomatic pattern. The mobile clients send
user-generated content (post text, search terms, display names) that must be treated as untrusted
at the Worker boundary regardless of any client-side validation.

---

## Parameterized Queries in D1

The D1 binding exposes `prepare()` → `bind()` → `run()` / `all()` / `first()`. Never interpolate
values into the SQL string.

```ts
// workers/src/db/posts.ts

// WRONG — SQL injection possible
export async function getPostBad(db: D1Database, postId: string) {
  return db.prepare(`SELECT * FROM posts WHERE id = '${postId}'`).all();
}

// CORRECT — parameterized
export async function getPost(db: D1Database, postId: string) {
  return db
    .prepare('SELECT id, body, created_at FROM posts WHERE id = ? AND deleted_at IS NULL')
    .bind(postId)
    .first<Post>();
}

// Multiple parameters — bind order matches ? order
export async function searchPosts(db: D1Database, term: string, limit: number) {
  const safeTerm = `%${term.replace(/%/g, '\\%').replace(/_/g, '\\_')}%`;
  return db
    .prepare(
      `SELECT id, body, created_at
       FROM posts
       WHERE body LIKE ? ESCAPE '\\'
         AND deleted_at IS NULL
       ORDER BY created_at DESC
       LIMIT ?`,
    )
    .bind(safeTerm, Math.min(limit, 100))
    .all<Post>();
}
```

LIKE wildcards (`%` and `_`) are not sanitised by parameterization — they must be escaped manually
before binding as shown above.

---

## Input Validation at the Worker Boundary

Parameterization stops injection; validation stops semantic abuse (e.g., extremely long strings
that cause D1 row-size issues, NUL bytes, or Unicode normalisation attacks).

```ts
// workers/src/lib/validate.ts
import { z } from 'zod';

export const PostCreateSchema = z.object({
  body: z
    .string()
    .min(1, 'Post cannot be empty')
    .max(500, 'Post body exceeds 500 characters')
    .refine((s) => !s.includes('\x00'), { message: 'NUL bytes not allowed' })
    .transform((s) => s.normalize('NFC').trim()),
  anonymous_name: z
    .string()
    .max(32)
    .regex(/^[\p{L}\p{N}\s._-]+$/u, 'Invalid characters in name')
    .optional(),
});

export const SearchSchema = z.object({
  q: z.string().min(2).max(100).trim(),
  page: z.coerce.number().int().min(1).max(1000).default(1),
  limit: z.coerce.number().int().min(1).max(50).default(20),
});

// Usage in Worker handler
export async function handleCreatePost(request: Request, env: Env): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: 'Invalid JSON' }), { status: 400 });
  }

  const parsed = PostCreateSchema.safeParse(body);
  if (!parsed.success) {
    return new Response(JSON.stringify({ error: parsed.error.flatten() }), { status: 422 });
  }

  const post = await createPost(env.DB, parsed.data);
  return Response.json(post, { status: 201 });
}
```

---

## ORM vs Raw SQL in Workers

| Criterion                    | Raw D1 (`prepare/bind`)       | Drizzle ORM (D1 adapter)         | Kysely (D1 dialect)              |
|------------------------------|-------------------------------|----------------------------------|----------------------------------|
| Bundle size impact           | None (built-in binding)       | ~15 KB minified                  | ~20 KB minified                  |
| Parameterization             | Manual, explicit              | Automatic                        | Automatic                        |
| Type safety                  | Manual type assertion         | Full TypeScript inference        | Full TypeScript inference         |
| Dynamic query safety         | Must build carefully          | Query builder enforces safety    | Query builder enforces safety    |
| D1 batch support             | `db.batch([...])`             | Drizzle transactions map to batch| Requires manual batch wrapping   |
| LIKE escape                  | Manual                        | Manual (ORM passes through)      | Manual                           |
| Workers cold-start cost      | Negligible                    | Low                              | Low                              |
| Recommended for example project         | Simple CRUD endpoints         | Complex relational queries       | Medium complexity, typed         |

For example project's anonymous platform, Drizzle with D1 adapter is the recommended default for new
endpoints — it provides automatic parameterization with schema types that match D1's column types.

```ts
// drizzle/schema.ts
import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

export const posts = sqliteTable('posts', {
  id: text('id').primaryKey(),
  body: text('body').notNull(),
  authorToken: text('author_token').notNull(),
  createdAt: integer('created_at', { mode: 'timestamp' }).notNull(),
  deletedAt: integer('deleted_at', { mode: 'timestamp' }),
});

// workers/src/db/posts.drizzle.ts
import { drizzle } from 'drizzle-orm/d1';
import { like, isNull, desc } from 'drizzle-orm';
import { posts } from '../../drizzle/schema';

export async function searchPostsDrizzle(db: D1Database, term: string) {
  const orm = drizzle(db);
  return orm
    .select({ id: posts.id, body: posts.body, createdAt: posts.createdAt })
    .from(posts)
    .where(and(like(posts.body, `%${term}%`), isNull(posts.deletedAt)))
    .orderBy(desc(posts.createdAt))
    .limit(20)
    .all();
}
```

Even with Drizzle, LIKE wildcard metacharacter escaping is the caller's responsibility.

---

## OWASP A03 Controls for D1

| OWASP A03 Control                    | D1 Implementation                                        | Status for example project        |
|--------------------------------------|----------------------------------------------------------|------------------------|
| Use parameterized queries            | `db.prepare().bind()`                                    | Required               |
| Validate & encode all inputs         | Zod schema at Worker boundary                            | Required               |
| Use allow-list input validation      | Regex patterns for names, UUIDs for IDs                  | Required               |
| Use stored procedures (if available) | D1 does not support stored procedures                    | N/A                    |
| Escape special characters            | LIKE metachar escape; avoid for other cases              | Required for LIKE only |
| Principle of least privilege on DB   | D1 binding is per-Worker — no cross-Worker DB access     | Enforced by platform   |
| Error messages reveal no SQL         | Catch D1 errors, return generic 500, log internally      | Required               |

---

## Error Handling Without SQL Leakage

```ts
// workers/src/lib/dbError.ts
export function handleD1Error(err: unknown, ctx: string): Response {
  // Log full error internally
  console.error(`[D1 Error][${ctx}]`, err instanceof Error ? err.message : String(err));

  // Never surface D1 or SQLite error text to the client
  return new Response(
    JSON.stringify({ error: 'Database error', requestId: crypto.randomUUID() }),
    { status: 500, headers: { 'content-type': 'application/json' } },
  );
}

// Usage
try {
  const result = await getPost(env.DB, postId);
  if (!result) return new Response(null, { status: 404 });
  return Response.json(result);
} catch (err) {
  return handleD1Error(err, 'getPost');
}
```

SQLite error messages like `no such column`, `UNIQUE constraint failed`, or `near "OR": syntax
error` expose schema details to an attacker — always catch and rethrow as opaque errors.

---

## Anti-patterns

- String interpolation in any part of the SQL: `WHERE id = '${id}'` — use `?` binding always.
- Trusting client-side validation as the sole defence: mobile clients can be proxied; validate at
  the Worker boundary unconditionally.
- Logging raw SQL with bound values to Logpush in production: bind values may contain PII or
  secrets; log query shapes (prepared statement text) not values.
- Using `db.exec()` for user-influenced queries: `exec()` runs raw SQL strings and does not
  support parameterization — restrict it to migration scripts only.
- Assuming LIKE is safe with parameterization alone: `%` and `_` within a bound value still act
  as wildcards inside LIKE patterns.

## Gotchas

- D1 `batch()` runs statements in a single HTTP round-trip but each statement still requires
  individual `prepare().bind()` — batch does not change parameterization requirements.
- SQLite `INTEGER` columns accept text without error at the D1 API level; validate numeric IDs
  as numbers before binding to avoid silent type coercion issues.
- D1 does not support `RETURNING *` in all SQLite versions deployed — check the D1 changelog
  before relying on it; fall back to a subsequent `SELECT` by ID.
- Zod `.transform()` runs after `.parse()`, not before validation — ensure your strip/trim
  transforms do not hide injection payloads that were valid pre-transform.
- Unicode normalisation (`NFC`) can change string length; re-validate `.max()` after `.transform()`.

## Verification

```bash
# 1. Manual injection probe (expect 400/422, not 200 with extra rows)
curl -s "https://api.example.com/posts?q=%27+OR+%271%27%3D%271" | jq .error

# 2. OWASP ZAP active scan (CI gate)
docker run --rm -t ghcr.io/zaproxy/zaproxy:stable zap-api-scan.py \
  -t https://api.example.com/openapi.json \
  -f openapi \
  -r /tmp/zap-report.html

# 3. Unit test — parameterization (Vitest + miniflare)
# test/db/posts.test.ts — bind a classic injection payload, confirm zero rows returned
const result = await getPost(env.DB, "1' OR '1'='1");
expect(result).toBeNull();

# 4. Confirm no SQL in error responses
curl -s https://api.example.com/posts/nonexistent | jq .
# Must not contain "SQLite", "no such", "syntax error"
```

## Related

- `sql-injection-deep-dive.md`
- `sql-injection-prevention-detail.md`
- `owasp-top-10-2025.md`
- `owasp-api-top-10-2023.md`
- `mass-assignment-prevention.md`
- `select-star-data-leak.md`

## Sources

- Cloudflare D1 parameterized queries: https://developers.cloudflare.com/d1/worker-api/prepared-statements/
- OWASP A03 Injection: https://owasp.org/Top10/A03_2021-Injection/
- Drizzle ORM D1 adapter: https://orm.drizzle.team/docs/get-started/d1-new
- SQLite LIKE wildcards: https://www.sqlite.org/lang_expr.html#like
- Zod validation: https://zod.dev/
