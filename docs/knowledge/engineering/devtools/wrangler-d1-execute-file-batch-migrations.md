# Wrangler D1 Execute File Batch Migrations

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a `/migrations` folder with numbered SQL files and want to apply them to D1
in CI or a deploy script without manually copy-pasting SQL. You've seen the
`wrangler d1 execute` command but aren't sure how to run multiple files reliably,
handle already-applied migrations, or validate the result before deploy.

---

## Context

`wrangler d1 execute` accepts either an inline `--command` string or a `--file` path.
It does **not** auto-discover or track applied migrations the way Flyway or Liquibase
do — that tracking is your responsibility. The standard pattern is a `migrations` table
in D1 itself plus a shell loop that skips already-applied files by name. Wrangler sends
each file as a single HTTP request; the Worker runtime splits on `;` and runs statements
as an implicit batch — meaning the file either fully succeeds or rolls back.

---

## Minimal migration table

```sql
-- migrations/0000_init_migrations_table.sql
CREATE TABLE IF NOT EXISTS _migrations (
  name       TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Apply once at bootstrap:

```bash
wrangler d1 execute MY_DB \
  --file migrations/0000_init_migrations_table.sql \
  --remote
```

---

## Shell script: apply pending migrations

```bash
#!/usr/bin/env bash
# scripts/migrate.sh
set -euo pipefail

DB_NAME="${1:?Usage: migrate.sh <db-name> [--remote|--local]}"
MODE="${2:---local}"   # default to local; pass --remote for production

MIGRATIONS_DIR="$(cd "$(dirname "$0")/../migrations" && pwd)"

echo "Applying migrations to '$DB_NAME' ($MODE) from $MIGRATIONS_DIR"

for file in "$MIGRATIONS_DIR"/*.sql; do
  name="$(basename "$file")"

  # Check if already applied
  applied=$(wrangler d1 execute "$DB_NAME" $MODE \
    --command "SELECT name FROM _migrations WHERE name = '${name}';" \
    --json 2>/dev/null | jq -r '.[0].results[0].name // empty')

  if [ "$applied" = "$name" ]; then
    echo "  SKIP  $name"
    continue
  fi

  echo "  APPLY $name"
  wrangler d1 execute "$DB_NAME" $MODE --file "$file"

  # Record as applied
  wrangler d1 execute "$DB_NAME" $MODE \
    --command "INSERT INTO _migrations (name) VALUES ('${name}');"

  echo "  DONE  $name"
done

echo "All migrations applied."
```

Usage:

```bash
# Local dev
bash scripts/migrate.sh MY_DB --local

# Production in CI
bash scripts/migrate.sh MY_DB --remote
```

---

## TypeScript version (Node.js script)

Useful when you need programmatic control over error handling or want to integrate with
a deploy pipeline written in TypeScript.

```typescript
// scripts/migrate.ts
import { execSync } from 'node:child_process'
import { readdirSync } from 'node:fs'
import { resolve, basename } from 'node:path'

const DB_NAME = process.env.D1_DATABASE ?? 'MY_DB'
const MODE    = process.env.D1_REMOTE === '1' ? '--remote' : '--local'
const MIGRATIONS_DIR = resolve(__dirname, '../migrations')

function d1(command: string): string {
  return execSync(
    `wrangler d1 execute ${DB_NAME} ${MODE} --command ${JSON.stringify(command)} --json`,
    { encoding: 'utf8' },
  )
}

function d1File(file: string): void {
  execSync(`wrangler d1 execute ${DB_NAME} ${MODE} --file ${JSON.stringify(file)}`, {
    stdio: 'inherit',
  })
}

async function main() {
  const files = readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith('.sql'))
    .sort()

  for (const name of files) {
    const raw = d1(`SELECT name FROM _migrations WHERE name = '${name}';`)
    const rows: { name: string }[] = JSON.parse(raw)[0]?.results ?? []

    if (rows.some((r) => r.name === name)) {
      console.log(`  SKIP  ${name}`)
      continue
    }

    console.log(`  APPLY ${name}`)
    d1File(resolve(MIGRATIONS_DIR, name))
    d1(`INSERT INTO _migrations (name) VALUES ('${name}');`)
    console.log(`  DONE  ${name}`)
  }
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
```

Run with `ts-node` or `tsx`:

```bash
D1_REMOTE=1 D1_DATABASE=MY_DB tsx scripts/migrate.ts
```

---

## GitHub Actions integration

```yaml
# .github/workflows/deploy.yml (relevant job step)
- name: Run D1 migrations
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
    CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
  run: |
    bash scripts/migrate.sh MY_DB --remote

- name: Deploy Worker
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  run: wrangler deploy
```

Order matters: migrations must complete before the new Worker code goes live so the
schema matches what the code expects.

---

## Dry-run / diff before applying

```bash
# List pending migrations without applying
for file in migrations/*.sql; do
  name="$(basename "$file")"
  applied=$(wrangler d1 execute MY_DB --remote \
    --command "SELECT name FROM _migrations WHERE name = '${name}';" \
    --json | jq -r '.[0].results[0].name // empty')
  [ -z "$applied" ] && echo "PENDING: $name"
done
```

---

## Anti-patterns

- **Running `--file` with multiple statements that share state** without wrapping in a
  transaction — D1 does wrap each file execution in a transaction, but explicit
  `BEGIN`/`COMMIT` in the file takes precedence and can conflict.
- **Using `--command` for large migrations** — the shell will hit argument-length limits
  above a few KB; always use `--file` for anything beyond a one-liner.
- **Storing migration state outside D1** (e.g. a file in the repo) — state diverges
  when multiple environments share the same repo but have different schemas.
- **No sorting** on file names — alphabetic sort of `0001_`, `0002_` is stable;
  timestamps or arbitrary names are not.

---

## Gotchas

- `wrangler d1 execute --json` output is an array; index `[0].results` to get rows.
  The shape changed between Wrangler 3 and Wrangler 4 — always check with
  `jq '.[0] | keys'` when upgrading.
- `--local` uses a SQLite file in `.wrangler/state/`; `--remote` hits the live D1 API.
  Never mix them in the same migration run.
- D1 does not support `ALTER TABLE … ADD COLUMN … AFTER …` — SQLite constraint. Use
  `ALTER TABLE t ADD COLUMN c TEXT` (appends to end) or recreate the table.
- The `_migrations` table name is a convention; Wrangler itself does not read it.

---

## Verification

```bash
# List applied migrations in local dev
wrangler d1 execute MY_DB --local \
  --command "SELECT * FROM _migrations ORDER BY applied_at;" \
  --json | jq '.[0].results'

# Confirm idempotent: run script twice, expect no new rows second time
bash scripts/migrate.sh MY_DB --local
bash scripts/migrate.sh MY_DB --local
# Should print only "SKIP" lines on the second run
```

---

## Related

- `wrangler-d1-migrations-local-dev-workflow.md`
- `vitest-global-setup-d1-migration-runner.md`
- `vitest-workers-d1-fixture-factories.md`
- `wrangler-dev-local-d1-r2-kv.md`

---

## Sources

- https://developers.cloudflare.com/d1/reference/migrations/
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
