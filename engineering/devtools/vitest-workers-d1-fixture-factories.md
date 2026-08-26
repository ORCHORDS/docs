# Vitest Workers D1 Test Fixture Factories

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have multiple Vitest test suites that all need a seeded D1 database, but each test
file manually inserts rows and cleans up in `beforeEach`/`afterEach`. The setup code is
duplicated across 15 files, migration order is fragile, and parallel test runs corrupt
each other's data.

**Goal:** factory functions that produce typed, isolated D1 fixture rows and tear
themselves down automatically, shared across the whole `@cloudflare/vitest-pool-workers`
suite without leaking state.

---

## Context

`@cloudflare/vitest-pool-workers` gives each worker its own in-process Miniflare
instance. Within a single worker the D1 binding is shared across tests in that file,
so isolation must be explicit. Factory helpers that return both the created record and a
`cleanup()` callback are the most composable pattern — they avoid global state and work
whether you call them in `beforeEach` or inside individual `it` blocks.

---

## Project structure

```
src/
  db/schema.ts          # Drizzle or raw SQL column definitions
  test/
    fixtures/
      index.ts          # re-exports all factories
      users.ts
      posts.ts
    helpers/
      db.ts             # migration runner + truncate helpers
vitest.config.ts
wrangler.toml
```

---

## Migration helper (run once per worker file)

```typescript
// src/test/helpers/db.ts
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { D1Database } from '@cloudflare/workers-types'

export async function runMigrations(db: D1Database): Promise<void> {
  const migrations = [
    '0001_create_users.sql',
    '0002_create_posts.sql',
  ]
  for (const file of migrations) {
    const sql = readFileSync(resolve(__dirname, '../../../migrations', file), 'utf8')
    // D1 executes the whole file as a batch when you split on semicolons
    const statements = sql
      .split(';')
      .map((s) => s.trim())
      .filter(Boolean)
    await db.batch(statements.map((s) => db.prepare(s)))
  }
}

export async function truncateTables(db: D1Database, tables: string[]): Promise<void> {
  await db.batch(
    tables.map((t) => db.prepare(`DELETE FROM ${t}`)),
  )
}
```

---

## Base factory type

```typescript
// src/test/fixtures/index.ts
import type { D1Database } from '@cloudflare/workers-types'

export interface Fixture<T> {
  data: T
  cleanup: () => Promise<void>
}

export type FactoryFn<T, Overrides = Partial<T>> = (
  db: D1Database,
  overrides?: Overrides,
) => Promise<Fixture<T>>
```

---

## User factory

```typescript
// src/test/fixtures/users.ts
import type { D1Database } from '@cloudflare/workers-types'
import type { Fixture } from './index'

export interface UserRow {
  id: number
  email: string
  name: string
  created_at: string
}

let _seq = 1

export async function createUser(
  db: D1Database,
  overrides: Partial<Omit<UserRow, 'id' | 'created_at'>> = {},
): Promise<Fixture<UserRow>> {
  const seq = _seq++
  const email = overrides.email ?? `user-${seq}@example.com`
  const name  = overrides.name  ?? `Test User ${seq}`

  const result = await db
    .prepare('INSERT INTO users (email, name) VALUES (?, ?) RETURNING *')
    .bind(email, name)
    .first<UserRow>()

  if (!result) throw new Error('INSERT INTO users returned no row')

  return {
    data: result,
    cleanup: async () => {
      await db.prepare('DELETE FROM users WHERE id = ?').bind(result.id).run()
    },
  }
}
```

---

## Post factory (with FK dependency)

```typescript
// src/test/fixtures/posts.ts
import type { D1Database } from '@cloudflare/workers-types'
import { createUser } from './users'
import type { Fixture } from './index'

export interface PostRow {
  id: number
  author_id: number
  title: string
  body: string
}

export async function createPost(
  db: D1Database,
  overrides: Partial<Omit<PostRow, 'id'>> = {},
): Promise<Fixture<PostRow>> {
  // Automatically create a parent user if author_id not supplied
  let authorFixture: Fixture<{ id: number }> | null = null
  let authorId = overrides.author_id

  if (!authorId) {
    authorFixture = await createUser(db)
    authorId = authorFixture.data.id
  }

  const title = overrides.title ?? 'Test Post'
  const body  = overrides.body  ?? 'example text'

  const result = await db
    .prepare('INSERT INTO posts (author_id, title, body) VALUES (?, ?, ?) RETURNING *')
    .bind(authorId, title, body)
    .first<PostRow>()

  if (!result) throw new Error('INSERT INTO posts returned no row')

  return {
    data: result,
    cleanup: async () => {
      await db.prepare('DELETE FROM posts WHERE id = ?').bind(result.id).run()
      await authorFixture?.cleanup()
    },
  }
}
```

---

## Using factories in a test file

```typescript
// src/workers/posts.test.ts
import { env, SELF } from 'cloudflare:test'
import { beforeAll, afterEach, describe, it, expect } from 'vitest'
import { runMigrations } from '../test/helpers/db'
import { createPost } from '../test/fixtures/posts'
import type { Fixture, PostRow } from '../test/fixtures/index'

beforeAll(async () => {
  await runMigrations(env.DB)
})

describe('GET /posts/:id', () => {
  let postFixture: Fixture<PostRow>

  afterEach(async () => {
    await postFixture?.cleanup()
  })

  it('returns 200 with the post', async () => {
    postFixture = await createPost(env.DB, { title: 'Hello World' })

    const res = await SELF.fetch(`http://example.com/posts/${postFixture.data.id}`)
    expect(res.status).toBe(200)

    const body = await res.json<PostRow>()
    expect(body.title).toBe('Hello World')
  })

  it('returns 404 for unknown id', async () => {
    // no fixture needed — no cleanup registered
    const res = await SELF.fetch('http://example.com/posts/99999')
    expect(res.status).toBe(404)
  })
})
```

---

## Anti-patterns

- **`beforeAll` inserts + `afterAll` truncate** — test ordering determines whether row
  IDs are predictable; a single failure skips truncation and poisons subsequent suites.
- **Hardcoding IDs** (`id: 1`) — parallel workers re-use the same auto-increment
  counter and collide silently.
- **`runMigrations` inside `beforeEach`** — re-running DDL on every test is ~10× slower;
  run it once per file in `beforeAll`.
- **Global mutable `_seq` without reset** — if you rely on sequence order across test
  files, wrap `_seq` in a `resetSeq()` export and call it in `beforeAll`.

---

## Gotchas

- `db.prepare(sql).first()` returns `null` when `RETURNING *` finds no row; always
  guard with a null check and throw.
- D1's batch API sends statements in a single transaction. If any statement fails the
  whole batch rolls back — useful for seeding, but means migration and seed must be
  separate `batch()` calls if you want partial rollback semantics.
- `@cloudflare/vitest-pool-workers` isolates each **worker file** but not individual
  `it` blocks within it; `cleanup()` must run in `afterEach`, not `afterAll`, if tests
  in the same file must not share rows.
- `env.DB` is only available inside the worker module context — you cannot import it
  in a Node.js helper file. Pass `db` as a parameter from the test file.

---

## Verification

```bash
# Run just the D1-related test files with verbose output
pnpm vitest run --reporter=verbose src/workers/posts.test.ts

# Confirm no leaked rows by running twice back-to-back
pnpm vitest run src/workers/posts.test.ts && pnpm vitest run src/workers/posts.test.ts
```

Expected: both runs green, no "UNIQUE constraint failed" errors.

---

## Related

- `vitest-global-setup-d1-migration-runner.md`
- `miniflare-d1-test-seeding-fixtures.md`
- `wrangler-d1-execute-file-batch-migrations.md`
- `vitest-pool-workers-cloudflare-test-api.md`

---

## Sources

- https://developers.cloudflare.com/workers/testing/vitest-integration/
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- https://miniflare.dev/storage/d1
