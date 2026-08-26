# feature-cookbook-data-modeling

**Issue:** Data modeling — schema, indexes, relationships
**Date:** 2026-08-09
**Status:** documented

## Symptom
You design a schema. You add columns. You add tables.
The schema grows. A query that took 10ms now takes 5
seconds. You add indexes. Some queries are fast; some
are still slow. You wish you'd designed the schema
better.

## Root cause
**Schema design is a skill.** A good schema considers
queries, indexes, and growth.

**Source:** Various data modeling guides.

## The "entity" pattern

For each entity, a table:
```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  display_name TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE posts (
  id TEXT PRIMARY KEY,
  author_id TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (author_id) REFERENCES users(id)
);
```

The tables are entities; the columns are attributes.

## The "primary key" pattern

For the primary key:
- **UUID:** Global unique, no info leak, slow insert
- **Auto-increment:** Sequential, easy to guess, fast
  insert
- **Composite:** Multi-column (for join tables)

For most apps, **UUID** is the right choice (no info
leak).

```ts
const id = crypto.randomUUID();
```

## The "index" pattern

For a frequently-queried column, add an index:
```sql
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_posts_author_id ON posts(author_id);
CREATE INDEX idx_posts_created_at ON posts(created_at DESC);
```

A query without an index is a full table scan.

## The "composite index" pattern

For a multi-column query:
```sql
-- Query: WHERE tenant_id = ? AND email = ?
CREATE INDEX idx_users_tenant_email ON users(tenant_id, email);
```

The column order matters: most selective first.

## The "covering index" pattern

For a query that reads only a few columns:
```sql
-- Query: SELECT id, email FROM users WHERE tenant_id = ?
CREATE INDEX idx_users_tenant_id_email ON users(tenant_id, id, email);
```

The index covers the query; no table read.

## The "foreign key" pattern

For a relationship:
```sql
CREATE TABLE posts (
  id TEXT PRIMARY KEY,
  author_id TEXT NOT NULL,
  -- ...
  FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
);
```

The FK enforces the relationship at the DB level.

## The "soft delete" pattern

For soft delete:
```sql
ALTER TABLE users ADD COLUMN deleted_at TEXT;
-- Soft delete: UPDATE users SET deleted_at = ? WHERE id = ?
-- Soft delete filter: WHERE deleted_at IS NULL
```

The row stays; the deleted_at is set.

## The "audit" columns

For every table:
```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  -- ... entity columns
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  created_by TEXT,
  updated_by TEXT
);
```

The audit columns track when + by whom.

## The "naming" convention

For consistent naming:
- **Tables:** plural, snake_case (`users`, `posts`)
- **Columns:** singular, snake_case (`email`, `created_at`)
- **Foreign keys:** `<table>_id` (`author_id`, `tenant_id`)
- **Timestamps:** `_at` suffix (`created_at`, `updated_at`)
- **Booleans:** `is_` or `has_` prefix (`is_active`,
  `has_verified_email`)

A consistent naming convention makes the schema readable.

## The "denormalization" pattern

For performance, denormalize (store the joined data):
```sql
-- Instead of:
SELECT u.display_name, p.title FROM users u JOIN posts p ON p.author_id = u.id;

-- Denormalize: store the display_name in the post
CREATE TABLE posts (
  id TEXT PRIMARY KEY,
  author_id TEXT NOT NULL,
  author_name TEXT NOT NULL,  -- Denormalized
  title TEXT,
  -- ...
);
```

Denormalization trades storage for speed.

## The "table partitioning" pattern

For huge tables, partition by date:
```sql
-- Posts partitioned by month
CREATE TABLE posts_2026_08 (
  -- ... columns
);
CREATE TABLE posts_2026_09 (
  -- ... columns
);
```

The query only hits the relevant partition.

## The "JSON column" pattern

For flexible data:
```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  metadata TEXT,  -- JSON: preferences, custom fields, etc.
);
```

Use JSON for data that doesn't need querying.

## The "enum" pattern

For fixed values:
```sql
CREATE TABLE posts (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK (status IN ('draft', 'published', 'archived')),
  -- ...
);
```

The CHECK constraint enforces the values.

## The "schema docs" pattern

For schema docs:
```markdown
## users
- `id` TEXT PK — UUID
- `email` TEXT NOT NULL — User's email
- `display_name` TEXT — User's display name
- `created_at` TEXT — ISO 8601

Indexes:
- `idx_users_email` ON (email)
- `idx_users_tenant` ON (tenant_id)

## posts
- `id` TEXT PK — UUID
- `author_id` TEXT NOT NULL — FK to users.id
- `title` TEXT NOT NULL
- `body` TEXT
- `status` TEXT NOT NULL — 'draft' | 'published' | 'archived'
- `created_at` TEXT — ISO 8601

Indexes:
- `idx_posts_author` ON (author_id)
- `idx_posts_status_created` ON (status, created_at DESC)
```

The docs are the schema's source of truth.

## The "schema migration" pattern

For schema changes, use migrations:
```sql
-- migrations/0001_initial.sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL
);

-- migrations/0002_add_display_name.sql
ALTER TABLE users ADD COLUMN display_name TEXT;
```

The migrations are versioned + applied in order.

## Verification
- **Test:** Schema is correct
- **Test:** Indexes are used (EXPLAIN)
- **Test:** Queries are fast (< 100ms p99)
- **Live:** Slow queries are monitored
- **Audit:** Annual schema review

## Gotchas
- **The "no index" anti-pattern.** A query without an
  index is slow.
- **The "index on every column" anti-pattern.** Too many
  indexes slow down writes.
- **The "no FK" anti-pattern.** A row with an invalid FK
  is a bug.
- **The "no audit columns" anti-pattern.** Without
  `created_at` / `updated_at`, debugging is hard.
- **The "no naming convention" anti-pattern.** Inconsistent
  naming is confusing.

## Related
- `database-migration-strategy.md`
- `database-index-strategies.md`
- `database-transaction-design.md`
- `soft-delete-pattern.md`
- `soft-delete-pattern-detail.md`
- `multi-tenant-data-isolation.md`
- `cloudflare/d1-migration-best-practices.md`
