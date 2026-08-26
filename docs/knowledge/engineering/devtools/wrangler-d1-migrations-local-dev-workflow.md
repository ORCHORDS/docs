# Wrangler D1 Migrations Local Dev Workflow

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your team runs `wrangler d1 migrations apply` in CI but local dev databases
drift because developers forget to apply new migration files after pulling. The
local SQLite file in `.wrangler/state/v3/d1/` accumulates manual schema tweaks
that are never codified, and the staging database gets out of sync when
migrations run in a different order on different machines.

---

## Context

Wrangler manages D1 migrations as numbered SQL files inside a configurable
directory (default `migrations/`). The `apply` command tracks which files have
been applied in a `d1_migrations` table. For local dev, wrangler writes a
SQLite file under `.wrangler/state/v3/d1/<DB_ID>/db.sqlite`; this is separate
from the remote D1 instance. Key commands:

| Command | Effect |
|---|---|
| `wrangler d1 migrations create` | Scaffold a new numbered SQL file |
| `wrangler d1 migrations list` | Show applied / pending status |
| `wrangler d1 migrations apply --local` | Apply pending to local SQLite |
| `wrangler d1 migrations apply` | Apply pending to remote D1 |
| `wrangler d1 execute --local --command "…"` | Run ad-hoc SQL locally |

---

## 1. Project Layout

```
project/
├── migrations/
│   ├── 0001_create_users.sql
│   ├── 0002_add_sessions.sql
│   └── 0003_add_preferences.sql
├── wrangler.toml
└── src/
    └── index.ts
```

```toml
# wrangler.toml
[[d1_databases]]
binding        = "DB"
database_name  = "my-app"
database_id    = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
migrations_dir = "migrations"
```

---

## 2. Creating Migration Files

```bash
# Always use wrangler to create — it picks the next number automatically
wrangler d1 migrations create my-app "add preferences table"
# → creates migrations/0003_add_preferences_table.sql
```

```sql
-- migrations/0003_add_preferences_table.sql
-- Up migration only; D1 does not support "down" migrations natively
CREATE TABLE IF NOT EXISTS preferences (
  user_id   TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  theme     TEXT NOT NULL DEFAULT 'system',
  locale    TEXT NOT NULL DEFAULT 'en',
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (user_id)
);

CREATE INDEX IF NOT EXISTS idx_preferences_user ON preferences(user_id);
```

---

## 3. Applying Migrations Locally

```bash
# Apply all pending migrations to the local SQLite
wrangler d1 migrations apply my-app --local

# Check what was applied (shows migration name and applied timestamp)
wrangler d1 migrations list my-app --local
```

```typescript
// scripts/migrate-local.ts — run before vitest or integration tests
import { execSync } from "node:child_process";

function applyLocalMigrations(dbName: string) {
  const out = execSync(`wrangler d1 migrations apply ${dbName} --local`, {
    encoding: "utf8",
    stdio: ["inherit", "pipe", "pipe"],
  });
  const applied = [...out.matchAll(/Applying migration (.+)/g)].map(
    (m) => m[1]
  );
  if (applied.length > 0) {
    console.log(`[migrate] Applied: ${applied.join(", ")}`);
  } else {
    console.log("[migrate] No pending migrations.");
  }
}

applyLocalMigrations("my-app");
```

---

## 4. Seeding After Migration

```typescript
// scripts/seed-local.ts
import { execSync } from "node:child_process";

const SEED_SQL = `
  INSERT OR IGNORE INTO users (id, email) VALUES
    ('u1', 'alice@example.com'),
    ('u2', 'bob@example.com');
  INSERT OR IGNORE INTO preferences (user_id, theme) VALUES
    ('u1', 'dark'),
    ('u2', 'light');
`;

execSync(
  `wrangler d1 execute my-app --local --command "${SEED_SQL.replace(/"/g, '\\"')}"`,
  { stdio: "inherit" }
);
console.log("[seed] Seed data inserted.");
```

```json
// package.json
{
  "scripts": {
    "db:reset": "rm -rf .wrangler/state/v3/d1 && pnpm db:migrate && pnpm db:seed",
    "db:migrate": "wrangler d1 migrations apply my-app --local",
    "db:seed": "node --import tsx/esm scripts/seed-local.ts",
    "test": "pnpm db:migrate && vitest run"
  }
}
```

---

## 5. Verifying Migration State in Tests

```typescript
// tests/helpers/db.ts
import { Miniflare } from "miniflare";

export async function getMigrationTable(mf: Miniflare, binding: string) {
  const db = await mf.getD1Database(binding);
  const { results } = await db
    .prepare("SELECT name, applied_at FROM d1_migrations ORDER BY id")
    .all<{ name: string; applied_at: string }>();
  return results;
}
```

```typescript
// tests/schema.test.ts
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { Miniflare } from "miniflare";
import { getMigrationTable } from "./helpers/db.js";
import { readdirSync } from "node:fs";

let mf: Miniflare;

beforeAll(async () => {
  mf = new Miniflare({
    modules: true,
    scriptPath: "dist/worker.js",
    d1Databases: ["DB"],
    // Apply migrations via wrangler before tests; miniflare reads the sqlite file
    d1Persist: ".wrangler/state/v3/d1",
  });
  await mf.ready;
});

afterAll(() => mf.dispose());

it("all migration files are applied", async () => {
  const applied = await getMigrationTable(mf, "DB");
  const files = readdirSync("migrations").filter((f) => f.endsWith(".sql"));

  expect(applied.map((r) => r.name).sort()).toEqual(files.sort());
});
```

---

## 6. CI Pipeline Integration

```yaml
# .github/workflows/test.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Apply local D1 migrations
        run: pnpm wrangler d1 migrations apply my-app --local
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Run tests
        run: pnpm test
```

```bash
# Detect migration drift in CI: fail if generated schema doesn't match current
wrangler d1 execute my-app --local --command ".schema" > /tmp/current-schema.sql
diff migrations/expected-schema.sql /tmp/current-schema.sql && echo "Schema OK"
```

---

## 7. Rolling Back Locally (Manual Technique)

D1 has no built-in rollback. The recommended local approach:

```bash
# 1. Delete the local state to start from scratch
rm -rf .wrangler/state/v3/d1

# 2. Re-apply only up to the last known-good migration
#    (comment out or remove newer files temporarily)
wrangler d1 migrations apply my-app --local

# 3. Or restore from a snapshot you kept:
cp .wrangler/state/v3/d1/backup-2026-08-20.sqlite \
   .wrangler/state/v3/d1/<DB_ID>/db.sqlite
```

---

## Anti-patterns

- **Hand-editing `.wrangler/state/v3/d1/*/db.sqlite`** – Changes are not
  tracked and will be wiped on the next `db:reset`.
- **Using `wrangler d1 execute` to apply schema changes** – Bypasses the
  migration tracker; the change won't be in `d1_migrations` and will be
  re-applied or skipped unpredictably.
- **Checking in the `.wrangler/` directory** – Contains machine-local state;
  always add to `.gitignore`.
- **Skipping `--local` flag in dev scripts** – Without `--local`, the command
  targets the remote D1 instance and may run against production data.

---

## Gotchas

- Migration file names must start with a sequential number prefix
  (`0001_`, `0002_` …). Wrangler sorts them lexicographically, not numerically,
  so `0010_` comes before `0009_` if you pad inconsistently.
- The `d1_migrations` table is created automatically on first `apply`; do not
  create it manually.
- D1 local mode uses SQLite 3, which lacks some Postgres-isms (e.g., `ILIKE`,
  `gen_random_uuid()`). Use `LOWER()` and `hex(randomblob(16))` instead.
- `--local` in Wrangler 3+ points at `.wrangler/state/v3/d1`. Older projects
  may use `.wrangler/state/d1` (v2 path); check your Wrangler version.

---

## Verification

```bash
# Confirm the migration table tracks all files
wrangler d1 migrations list my-app --local

# Spot-check a table exists after migration
wrangler d1 execute my-app --local \
  --command "SELECT name FROM sqlite_master WHERE type='table';"
```

---

## Related

- `wrangler-dev-local-d1-r2-kv.md`
- `miniflare-d1-test-seeding-fixtures.md`
- `wrangler-dev-local-d1-r2-testing.md`
- `vitest-workers-miniflare-testing-setup.md`

---

## Sources

- Wrangler D1 migrations docs: https://developers.cloudflare.com/d1/reference/migrations/
- D1 local dev guide: https://developers.cloudflare.com/d1/configuration/local-development/
- wrangler CLI reference: https://developers.cloudflare.com/workers/wrangler/commands/#d1
