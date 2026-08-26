# Cloudflare D1 Import/Export via Wrangler — Migration Snapshots & CI/CD

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) engineers need to: (a) seed a fresh D1 database from a SQL dump, (b) snapshot production data before a destructive migration, (c) detect schema drift between environments, and (d) automate all of the above in a GitHub Actions pipeline. The `wrangler d1 export` and `wrangler d1 execute` commands have non-obvious flags and the import flow requires a pre-upload step that is easy to skip.

## Context

D1 supports SQL-level import and export through Wrangler CLI. There is no binary dump (`.sqlite3` file transfer) in the public API — data moves as plain SQL text (DDL + DML). Exports go to R2 or are streamed locally depending on the database size. Imports execute a SQL file against the database via the D1 HTTP API, not through a local SQLite connection.

example project runs three environments: `local` (Miniflare / `wrangler dev`), `staging` (`example project-d1-staging`), and `prod` (`example project-d1-prod`). Migration files live in `db/migrations/`.

## Export — Full Database Dump

```bash
# Export schema + data to a local file
wrangler d1 export example project-d1-prod \
  --output ./snapshots/prod-$(date +%Y%m%d-%H%M%S).sql

# Export schema only (no INSERT statements)
wrangler d1 export example project-d1-prod \
  --output ./snapshots/schema-only.sql \
  --no-data

# Export a single table
wrangler d1 export example project-d1-prod \
  --table recordings \
  --output ./snapshots/recordings.sql
```

`--output` is required; without it the dump streams to stdout which is fine for piping but loses progress indicators. For databases > ~50 MB the export is staged through an internal R2 bucket and downloaded as a pre-signed URL — Wrangler handles this transparently.

Export flag reference:

| Flag | Default | Effect |
|---|---|---|
| `--output` | stdout | Local file path |
| `--no-data` | false | Schema DDL only |
| `--no-schema` | false | Data INSERT rows only |
| `--table <name>` | all tables | Single-table dump |
| `--remote` | true | Always targets remote D1 |
| `--local` | false | Export from local Miniflare DB |

## Import — Seeding and Restoring

```bash
# Import a SQL dump into a database (destructive if dump drops/recreates tables)
wrangler d1 execute example project-d1-staging \
  --remote \
  --file ./snapshots/prod-20260822-120000.sql

# Import with verbose output (shows each statement executed)
wrangler d1 execute example project-d1-staging \
  --remote \
  --file ./snapshots/seed.sql \
  --json
```

Large imports (> 10 MB SQL): Wrangler automatically splits and batches statements. If the file contains explicit `BEGIN`/`COMMIT` wrappers, Wrangler preserves them. Do not manually split by newline — rely on the CLI.

Import gotcha — files with `PRAGMA foreign_keys = ON` at the top can fail if the import inserts child rows before parent rows (a dump ordering issue). Add at the top of your seed file:

```sql
PRAGMA defer_foreign_keys = ON;
```

This defers FK checks until the end of each transaction, resolving insert-order problems.

## Migration Snapshot Workflow

Pre-migration snapshot pattern used in example project CI:

```bash
#!/usr/bin/env bash
# scripts/pre-migrate-snapshot.sh
set -euo pipefail

DB_NAME="${1:-example project-d1-prod}"
SNAPSHOT_DIR="./snapshots"
mkdir -p "$SNAPSHOT_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
SNAPSHOT_FILE="$SNAPSHOT_DIR/${DB_NAME}-pre-migrate-${TIMESTAMP}.sql"

echo "Snapshotting $DB_NAME -> $SNAPSHOT_FILE"
wrangler d1 export "$DB_NAME" --output "$SNAPSHOT_FILE"

# Optionally upload to R2 for long-term retention
wrangler r2 object put "example project-db-snapshots/${DB_NAME}/${TIMESTAMP}.sql" \
  --file "$SNAPSHOT_FILE"

echo "Snapshot complete: $SNAPSHOT_FILE"
```

Rollback from snapshot:

```bash
# DESTRUCTIVE: re-imports entire snapshot, overwriting all current data
wrangler d1 execute example project-d1-prod \
  --remote \
  --file ./snapshots/example project-d1-prod-pre-migrate-20260822-115900.sql
```

Because D1 has Time Travel (PITR) for the last 30 days on paid plans, a snapshot is a human-readable complement — not a replacement — for PITR. Use PITR for fast automated rollback; use SQL snapshots for portability and inspection.

## Schema Drift Detection

Drift = the schema in a migration file differs from what is live in the DB. Common cause: manual `ALTER TABLE` in prod console, or migration applied out of order.

Script to detect drift:

```bash
#!/usr/bin/env bash
# scripts/check-schema-drift.sh
# Compares live schema to the expected schema built from migration files

EXPECTED_SCHEMA="./snapshots/expected-schema.sql"
LIVE_SCHEMA="./snapshots/live-schema.sql"

# Build expected schema by running migrations against a fresh local DB
wrangler d1 execute example project-d1-local \
  --local \
  --file ./db/migrations/0001_init.sql
# ... (loop all migration files in order)

wrangler d1 export example project-d1-local --local --no-data --output "$EXPECTED_SCHEMA"

# Pull live schema
wrangler d1 export example project-d1-prod --no-data --output "$LIVE_SCHEMA"

# Normalise and diff (strip comments, sort CREATE TABLE blocks)
python3 scripts/normalise_schema.py "$EXPECTED_SCHEMA" > /tmp/expected_norm.sql
python3 scripts/normalise_schema.py "$LIVE_SCHEMA" > /tmp/live_norm.sql

diff /tmp/expected_norm.sql /tmp/live_norm.sql && echo "No drift" || {
  echo "SCHEMA DRIFT DETECTED"
  exit 1
}
```

Minimal `normalise_schema.py` — removes comments and normalises whitespace:

```python
import re, sys

with open(sys.argv[1]) as f:
    sql = f.read()

# Remove SQL comments
sql = re.sub(r'--[^\n]*', '', sql)
sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
# Normalise whitespace
sql = re.sub(r'\s+', ' ', sql).strip()
print(sql)
```

For production use, consider `sqldiff` (SQLite CLI tool) or `dbmate diff`.

## CI/CD Pipeline — GitHub Actions

```yaml
# .github/workflows/db-migrate.yml
name: D1 Migration

on:
  push:
    branches: [main]
    paths: ['db/migrations/**']

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install Wrangler
        run: npm install -g wrangler@latest

      - name: Snapshot before migration
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_D1_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          wrangler d1 export example project-d1-prod \
            --output ./pre-migrate-snapshot.sql

      - name: Upload snapshot artifact
        uses: actions/upload-artifact@v4
        with:
          name: pre-migrate-snapshot
          path: pre-migrate-snapshot.sql
          retention-days: 30

      - name: Apply new migrations
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_D1_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          # Apply only new migrations (tracked by a migrations table)
          for f in db/migrations/*.sql; do
            NAME=$(basename "$f")
            EXISTS=$(wrangler d1 execute example project-d1-prod --remote --json \
              --command "SELECT name FROM _migrations WHERE name='$NAME'" \
              | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d[0]['results']))")
            if [ "$EXISTS" = "0" ]; then
              echo "Applying $NAME"
              wrangler d1 execute example project-d1-prod --remote --file "$f"
              wrangler d1 execute example project-d1-prod --remote --json \
                --command "INSERT INTO _migrations(name, applied_at) VALUES('$NAME', datetime('now'))"
            fi
          done

      - name: Verify row counts post-migration
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_D1_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          wrangler d1 execute example project-d1-prod --remote --json \
            --command "SELECT name, (SELECT COUNT(*) FROM sqlite_master WHERE type='table') as tables"
```

API token for the CI job needs only:

| Permission | Scope |
|---|---|
| D1 | Edit (for execute) |
| D1 | Read (for export) |
| R2 | Edit (if uploading snapshots to R2) |

Use `CF_D1_API_TOKEN` as a GitHub secret; never use the Global API Key.

## Anti-patterns

- Running `wrangler d1 execute` without `--remote` against the wrong environment — local and remote are completely separate DBs; the flag is easy to omit.
- Using `--command` for large SQL strings in CI — shell quoting breaks; always use `--file`.
- Storing snapshot SQL files in the git repository — they can contain PII; use artifact storage or R2 instead.
- Skipping the pre-migration snapshot because Time Travel exists — PITR requires Cloudflare Dashboard access; a SQL file can be restored anywhere, including locally.
- Applying all migration files on every CI run without tracking applied migrations — idempotent migrations with `IF NOT EXISTS` help, but a `_migrations` ledger table is more robust.

## Gotchas

- **`wrangler d1 export` output is not a `.sqlite3` binary**: it is plain SQL text. You cannot open it directly with the sqlite3 CLI as a DB file (`sqlite3 dump.sql` fails). Import it with `.read dump.sql` or via `sqlite3 :memory: < dump.sql`.
- **Large exports time out in interactive terminals**: use `--output` to a file; streaming exports > 100 MB can hit the shell's buffer. Wrangler 3.x handles large exports via R2 staging automatically.
- **`AUTOINCREMENT` vs `INTEGER PRIMARY KEY`**: D1 exports use SQLite semantics. If your schema uses `AUTOINCREMENT`, the dump includes a `sqlite_sequence` table. Importing it into a fresh DB resets the sequence correctly, but if you import only the data (`--no-schema`) you must also import `sqlite_sequence` or IDs may collide.
- **Foreign key constraint order**: SQLite disables FK checks by default; the export does not emit `PRAGMA foreign_keys` statements. Add `PRAGMA foreign_keys = ON;` to your migration files explicitly.
- **D1 Time Travel and exports are complementary**: PITR bookmarks cannot be exported as SQL; they can only be restored to the same D1 instance via the Dashboard or API.

## Verification

```bash
# Confirm export produced a valid SQL file
head -5 ./snapshots/prod-20260822-120000.sql
# Expected first lines:
# PRAGMA foreign_keys=OFF;
# BEGIN TRANSACTION;
# CREATE TABLE ...

# Count tables in the dump
grep -c '^CREATE TABLE' ./snapshots/prod-20260822-120000.sql

# Verify import succeeded by checking a known table's row count
wrangler d1 execute example project-d1-staging --remote --json \
  --command "SELECT COUNT(*) as n FROM recordings"
```

## Related

- `d1-export-import.md` — earlier foundational export/import patterns
- `d1-migration-best-practices.md` — migration file conventions
- `d1-time-travel.md` — PITR rollback procedure
- `d1-best-practices.md` — overall D1 guidance for example project
- `r2-best-practices.md` — R2 as snapshot storage backend

## Sources

- Wrangler D1 export docs: https://developers.cloudflare.com/d1/wrangler-commands/#d1-export
- Wrangler D1 execute docs: https://developers.cloudflare.com/d1/wrangler-commands/#d1-execute
- D1 Time Travel: https://developers.cloudflare.com/d1/reference/time-travel/
- SQLite dump format: https://www.sqlite.org/cli.html#converting_an_entire_database_to_an_ascii_text_file
