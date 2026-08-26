# Testing D1 Schema Migrations with Vitest

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your D1 database migrations run fine in production but break silently in CI because test code talks to an un-migrated in-memory database. You need a deterministic, ordered migration runner inside Vitest so every test starts from the exact schema that production uses, including data migration scripts.

---

## Context

Cloudflare D1 stores migration SQL files in a directory (default `migrations/`) and tracks applied migrations in the `d1_migrations` system table. In a Vitest environment backed by `@cloudflare/vitest-pool-workers`, you get a fresh local D1 instance per worker pool — but migrations are NOT applied automatically. You must apply them programmatically using the Wrangler CLI or the D1 binding's `exec()` method. `PRAGMA table_info('<table>')` is the reliable cross-SQLite way to introspect column definitions without coupling tests to brittle `SELECT *` ordering. Snapshot testing column definitions catches accidental column renames or type changes that would otherwise only surface in production.

---

## Setup / Config

`wrangler.toml`:
```toml
[[d1_databases]]
binding = "DB"
database_name = "orchords-local"
database_id = "00000000-0000-0000-0000-000000000000"
migrations_dir = "migrations"
```

`vitest.config.ts`:
```typescript
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "./wrangler.toml" },
        miniflare: {
          d1Databases: ["DB"],
        },
      },
    },
  },
});
```

`migrations/0001_create_tracks.sql`:
```sql
CREATE TABLE IF NOT EXISTS tracks (
  id       TEXT PRIMARY KEY,
  title    TEXT NOT NULL,
  bpm      INTEGER,
  key      TEXT,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
```

`migrations/0002_add_genre.sql`:
```sql
ALTER TABLE tracks ADD COLUMN genre TEXT;
```

`src/lib/migrate.ts`:
```typescript
import fs from "node:fs/promises";
import path from "node:path";

export async function applyMigrations(
  db: D1Database,
  migrationsDir = "migrations"
): Promise<void> {
  // Ensure the migrations tracking table exists
  await db.exec(`
    CREATE TABLE IF NOT EXISTS d1_migrations (
      id          INTEGER PRIMARY KEY AUTOINCREMENT,
      name        TEXT    NOT NULL UNIQUE,
      applied_at  INTEGER NOT NULL DEFAULT (unixepoch())
    )
  `);

  const files = (await fs.readdir(migrationsDir))
    .filter((f) => f.endsWith(".sql"))
    .sort(); // lexicographic order mirrors Wrangler behaviour

  for (const file of files) {
    const already = await db
      .prepare("SELECT 1 FROM d1_migrations WHERE name = ?")
      .bind(file)
      .first();

    if (already) continue;

    const sql = await fs.readFile(path.join(migrationsDir, file), "utf8");
    await db.exec(sql);
    await db
      .prepare("INSERT INTO d1_migrations (name) VALUES (?)")
      .bind(file)
      .run();
  }
}
```

---

## Test Implementation

`src/lib/migrate.test.ts`:
```typescript
import { env } from "cloudflare:test";
import { describe, it, expect, beforeAll } from "vitest";
import { applyMigrations } from "./migrate";

// Shared fixture: a row inserted in a data-migration script
const SEED_TRACK = {
  id: "seed-001",
  title: "Test Track",
  bpm: 128,
  key: "Am",
};

describe("D1 migration suite", () => {
  beforeAll(async () => {
    // Apply all SQL files in migrations/ in order
    await applyMigrations(env.DB);
  });

  it("tracks table exists after migrations", async () => {
    const { results } = await env.DB.prepare(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='tracks'"
    ).all();
    expect(results).toHaveLength(1);
  });

  it("PRAGMA table_info matches expected columns", async () => {
    const { results } = await env.DB.prepare(
      "PRAGMA table_info('tracks')"
    ).all();

    // Snapshot the column definitions so renames/type changes are caught
    expect(results).toMatchInlineSnapshot(`
      [
        { "cid": 0, "dflt_value": null,          "name": "id",         "notnull": 1, "pk": 1, "type": "TEXT"    },
        { "cid": 1, "dflt_value": null,          "name": "title",      "notnull": 1, "pk": 0, "type": "TEXT"    },
        { "cid": 2, "dflt_value": null,          "name": "bpm",        "notnull": 0, "pk": 0, "type": "INTEGER" },
        { "cid": 3, "dflt_value": null,          "name": "key",        "notnull": 0, "pk": 0, "type": "TEXT"    },
        { "cid": 4, "dflt_value": "(unixepoch())", "name": "created_at", "notnull": 1, "pk": 0, "type": "INTEGER" },
        { "cid": 5, "dflt_value": null,          "name": "genre",      "notnull": 0, "pk": 0, "type": "TEXT"    },
      ]
    `);
  });

  it("d1_migrations table records each applied file", async () => {
    const { results } = await env.DB.prepare(
      "SELECT name FROM d1_migrations ORDER BY name"
    ).all<{ name: string }>();

    expect(results.map((r) => r.name)).toEqual([
      "0001_create_tracks.sql",
      "0002_add_genre.sql",
    ]);
  });

  it("data migration seed inserts correctly", async () => {
    // Simulate a data-migration script inserting a fixture row
    await env.DB.prepare(
      "INSERT INTO tracks (id, title, bpm, key) VALUES (?, ?, ?, ?)"
    )
      .bind(SEED_TRACK.id, SEED_TRACK.title, SEED_TRACK.bpm, SEED_TRACK.key)
      .run();

    const row = await env.DB.prepare(
      "SELECT * FROM tracks WHERE id = ?"
    )
      .bind(SEED_TRACK.id)
      .first<typeof SEED_TRACK & { genre: string | null; created_at: number }>();

    expect(row?.title).toBe("Test Track");
    expect(row?.bpm).toBe(128);
    expect(row?.genre).toBeNull();
    expect(typeof row?.created_at).toBe("number");
  });

  it("applying migrations twice is idempotent", async () => {
    // Should not throw or create duplicate entries
    await expect(applyMigrations(env.DB)).resolves.toBeUndefined();

    const { results } = await env.DB.prepare(
      "SELECT COUNT(*) as cnt FROM d1_migrations"
    ).all<{ cnt: number }>();
    expect(results[0].cnt).toBe(2);
  });
});
```

---

## Anti-patterns

- **Applying migrations with `wrangler d1 migrations apply` in a subprocess** — works but ties test speed to a CLI round-trip; use `db.exec()` inline instead.
- **Hard-coding expected column order** — SQLite does not guarantee column order across `ALTER TABLE` operations; always key assertions on the `name` field.
- **Sharing a single D1 binding across parallel test files** — writes from one suite pollute another; reset with `DELETE FROM <table>` in `afterEach` or use separate bindings per file.
- **Forgetting to sort migration filenames** — `fs.readdir` order is OS-dependent; always `.sort()` before iterating.

---

## Gotchas

- `db.exec()` does not support multiple statements separated by `;` in all SQLite builds — split on `;` if your migration files contain multiple statements.
- `PRAGMA table_info` returns `dflt_value` as a **string** (e.g. `"(unixepoch())"`) not a evaluated value; match it literally in snapshots.
- The local D1 instance created by `vitest-pool-workers` is ephemeral — it does **not** persist between `vitest` runs, so migrations re-run from zero each time.
- `ALTER TABLE … ADD COLUMN` cannot add a `NOT NULL` column without a `DEFAULT`; your migration will fail at test time the same as production — which is the desired behaviour.

---

## Verification

```bash
# Run only migration tests
npx vitest run src/lib/migrate.test.ts

# Update inline snapshots after intentional schema change
npx vitest run --update-snapshots src/lib/migrate.test.ts

# Check local schema via Wrangler
npx wrangler d1 execute orchords-local --local --command "PRAGMA table_info('tracks')"
```

---

## Related

- `workers-d1-query-testing-vitest.md`
- `workers-durable-objects-alarm-testing.md`

---

## Sources

- Cloudflare D1 Migrations Docs — https://developers.cloudflare.com/d1/reference/migrations/
- Vitest Pool Workers — https://developers.cloudflare.com/workers/testing/vitest-integration/
- SQLite PRAGMA table_info — https://www.sqlite.org/pragma.html#pragma_table_info
