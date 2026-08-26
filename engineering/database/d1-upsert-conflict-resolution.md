# Upsert Patterns with Conflict Resolution in Cloudflare D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker receives events or webhook payloads that may arrive more than once. You need to insert a row if it does not exist and update specific columns if it does, all in a single atomic statement. Separate `SELECT` + `INSERT` / `UPDATE` pairs create race conditions and waste round-trips to D1.

---

## Context

D1 (SQLite) supports `INSERT OR REPLACE`, `INSERT … ON CONFLICT DO NOTHING`, and the ANSI-standard `INSERT … ON CONFLICT(col) DO UPDATE SET …` (aka UPSERT). The `DO UPDATE SET` variant lets you update only the columns that should change while leaving others intact, and `excluded.*` refers to the values that were attempted in the failing insert. `RETURNING *` appends a result set to the statement, giving you the final row state without a follow-up SELECT. Compound unique constraints (multi-column) are handled the same way by listing all constrained columns in the `ON CONFLICT(...)` clause.

---

## Schema — Table with Unique Constraints

```sql
CREATE TABLE IF NOT EXISTS users (
  id           TEXT      PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  email        TEXT      NOT NULL,
  provider     TEXT      NOT NULL DEFAULT 'email',  -- 'email' | 'github' | 'google'
  display_name TEXT      NOT NULL DEFAULT '',
  avatar_url   TEXT,
  plan         TEXT      NOT NULL DEFAULT 'free',
  created_at   DATETIME  NOT NULL DEFAULT (datetime('now')),
  updated_at   DATETIME  NOT NULL DEFAULT (datetime('now')),
  -- A user is unique per (email, provider) pair — same email can sign in via
  -- multiple OAuth providers as separate accounts.
  UNIQUE (email, provider)
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
```

---

## Implementation

```typescript
// src/lib/upsert.ts
export interface UpsertUserInput {
  email: string;
  provider: 'email' | 'github' | 'google';
  display_name: string;
  avatar_url?: string | null;
}

export interface User {
  id: string;
  email: string;
  provider: string;
  display_name: string;
  avatar_url: string | null;
  plan: string;
  created_at: string;
  updated_at: string;
}

/**
 * Upsert a user by (email, provider).
 * - If no matching row exists, inserts with defaults.
 * - If the row exists, updates display_name, avatar_url, and updated_at.
 * - Returns the final persisted row via RETURNING *.
 */
export async function upsertUser(
  db: D1Database,
  input: UpsertUserInput
): Promise<User> {
  const now = new Date().toISOString();
  const { results } = await db
    .prepare(
      `INSERT INTO users (email, provider, display_name, avatar_url, updated_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(email, provider) DO UPDATE SET
         display_name = excluded.display_name,
         avatar_url   = excluded.avatar_url,
         updated_at   = excluded.updated_at
       RETURNING *`
    )
    .bind(
      input.email,
      input.provider,
      input.display_name,
      input.avatar_url ?? null,
      now
    )
    .all<User>();

  const user = results[0];
  if (!user) throw new Error('Upsert returned no rows — unexpected D1 error');
  return user;
}

/**
 * Idempotent insert: silently ignore if a row with the same email already
 * exists for the same provider. Returns null when no insert occurred.
 */
export async function insertUserIfAbsent(
  db: D1Database,
  input: UpsertUserInput
): Promise<User | null> {
  const now = new Date().toISOString();
  const { results } = await db
    .prepare(
      `INSERT INTO users (email, provider, display_name, avatar_url, updated_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(email, provider) DO NOTHING
       RETURNING *`
    )
    .bind(
      input.email,
      input.provider,
      input.display_name,
      input.avatar_url ?? null,
      now
    )
    .all<User>();

  return results[0] ?? null;
}

/**
 * Upsert on a single-column unique constraint.
 * Useful for settings or feature-flag rows keyed by a single natural key.
 */
export async function upsertSetting(
  db: D1Database,
  key: string,
  value: string
): Promise<{ key: string; value: string; updated_at: string }> {
  const now = new Date().toISOString();
  const { results } = await db
    .prepare(
      `INSERT INTO settings (key, value, updated_at)
       VALUES (?, ?, ?)
       ON CONFLICT(key) DO UPDATE SET
         value      = excluded.value,
         updated_at = excluded.updated_at
       RETURNING *`
    )
    .bind(key, value, now)
    .all<{ key: string; value: string; updated_at: string }>();

  return results[0]!;
}
```

---

## Testing / Verification

```typescript
// src/lib/upsert.test.ts
import { describe, it, expect, beforeEach } from 'vitest';
import { env } from 'cloudflare:test';
import { upsertUser, insertUserIfAbsent } from './upsert';

describe('upsertUser', () => {
  beforeEach(async () => {
    await env.DB.exec(`DELETE FROM users`);
  });

  it('inserts a new user and returns the row', async () => {
    const user = await upsertUser(env.DB, {
      email: 'alice@example.com',
      provider: 'github',
      display_name: 'Alice',
      avatar_url: 'https://example.com/alice.png',
    });
    expect(user.id).toBeTruthy();
    expect(user.plan).toBe('free');   // default preserved
    expect(user.email).toBe('alice@example.com');
  });

  it('updates display_name on second call, preserves plan and created_at', async () => {
    const first = await upsertUser(env.DB, {
      email: 'alice@example.com',
      provider: 'github',
      display_name: 'Alice',
    });

    // Simulate plan upgrade outside of upsert path
    await env.DB.prepare(`UPDATE users SET plan = 'pro' WHERE id = ?`).bind(first.id).run();

    const second = await upsertUser(env.DB, {
      email: 'alice@example.com',
      provider: 'github',
      display_name: 'Alice Updated',
    });

    expect(second.id).toBe(first.id);           // same row
    expect(second.plan).toBe('pro');             // not clobbered by upsert
    expect(second.display_name).toBe('Alice Updated');
    expect(second.created_at).toBe(first.created_at); // immutable
  });

  it('DO NOTHING returns null when row already exists', async () => {
    await upsertUser(env.DB, { email: 'b@b.com', provider: 'email', display_name: 'B' });
    const result = await insertUserIfAbsent(env.DB, { email: 'b@b.com', provider: 'email', display_name: 'B2' });
    expect(result).toBeNull();
  });

  it('same email different provider inserts two rows', async () => {
    await upsertUser(env.DB, { email: 'c@c.com', provider: 'github', display_name: 'C' });
    await upsertUser(env.DB, { email: 'c@c.com', provider: 'google', display_name: 'C' });
    const { results } = await env.DB.prepare(`SELECT COUNT(*) as n FROM users WHERE email = 'c@c.com'`).all<{ n: number }>();
    expect(results[0].n).toBe(2);
  });
});
```

---

## Anti-patterns

- **`INSERT OR REPLACE`** — this is a DELETE + INSERT under the hood; it reassigns the primary key, breaks foreign key references, and resets all default columns. Use `ON CONFLICT … DO UPDATE` instead.
- **SELECT then INSERT in separate statements** — creates a TOCTOU race condition; two concurrent requests can both observe no row and both attempt INSERT, causing one to fail.
- **Forgetting `excluded.*`** — writing `DO UPDATE SET updated_at = datetime('now')` instead of `excluded.updated_at` silently ignores the value you actually passed in, leading to skew between in-memory state and the DB row.
- **No `RETURNING *`** — without it you need a follow-up SELECT to read the final row, doubling the round-trips to D1.

---

## Gotchas

- `ON CONFLICT(col)` must exactly match a unique index or primary key; if the column list doesn't correspond to a real constraint, SQLite raises `SQLITE_ERROR`.
- `DO UPDATE SET` triggers any `AFTER UPDATE` triggers on the table; `DO NOTHING` does not trigger them — keep this in mind if you use triggers for audit logging.
- D1 does not yet support deferred constraints, so all unique constraint violations are immediate.
- `RETURNING *` returns columns in schema definition order, not insertion order — always use column aliases or map by name.

---

## Verification

```bash
# Inspect final row after upsert
wrangler d1 execute orchords-db --command "
  INSERT INTO users (email, provider, display_name, updated_at)
  VALUES ('test@example.com', 'email', 'Test User', datetime('now'))
  ON CONFLICT(email, provider) DO UPDATE SET
    display_name = excluded.display_name,
    updated_at   = excluded.updated_at
  RETURNING id, email, plan, updated_at;
"

# Verify row count stays 1 after duplicate attempts
wrangler d1 execute orchords-db --command "
  SELECT COUNT(*) FROM users WHERE email = 'test@example.com';
"
```

---

## Related

- `d1-soft-delete-restore-pattern.md`
- `d1-read-replica-binding.md`

---

## Sources

- SQLite UPSERT Documentation — https://www.sqlite.org/lang_UPSERT.html
- Cloudflare D1 Docs — https://developers.cloudflare.com/d1/
- Vitest Cloudflare Workers — https://developers.cloudflare.com/workers/testing/vitest-integration/
