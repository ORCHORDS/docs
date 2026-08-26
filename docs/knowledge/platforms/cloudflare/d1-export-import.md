# d1-export-import

**Issue:** Exporting and importing data from Cloudflare D1 databases
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
D1 does not yet have a native SQL dump UI, but you can export data via Wrangler commands and the REST API. This is useful for backups, migrations, and seeding environments.

## Pattern / Solution

**Export (dump) via Wrangler:**
```bash
# Export entire database as SQLite file (binary)
wrangler d1 export my-database --output ./backup.sqlite

# Export as SQL text (INSERT statements)
wrangler d1 export my-database --output ./backup.sql --format sql

# Export a specific table only
wrangler d1 export my-database --table users --output ./users.sql
```

**Import from SQL file:**
```bash
# Apply a SQL file to the database (runs as a migration)
wrangler d1 execute my-database --file ./seed.sql

# Import to remote database
wrangler d1 execute my-database --file ./seed.sql --remote
```

**Import from SQLite binary file:**
```bash
# Currently not supported natively — convert to SQL first
sqlite3 backup.sqlite .dump > backup.sql
wrangler d1 execute my-database --file backup.sql --remote
```

**Programmatic export via REST API:**
```bash
# Step 1: start the export
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/d1/database/$DB_ID/export" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"outputFormat": "polling", "dumpOptions": {"noSchema": false, "noData": false, "tables": []}}'

# Step 2: poll until done (bookmark from step 1)
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/d1/database/$DB_ID/export" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"currentBookmark": "<bookmark-from-step-1>"}'

# Step 3: download the signed URL from the result
curl "<signed-s3-url>" -o backup.sql
```

**Seeding in Workers (for small datasets):**
```typescript
async function seed(env: Env): Promise<void> {
  await env.DB.batch([
    env.DB.prepare(`INSERT OR IGNORE INTO roles (name) VALUES (?)`).bind('admin'),
    env.DB.prepare(`INSERT OR IGNORE INTO roles (name) VALUES (?)`).bind('user'),
  ]);
}
```

## Gotchas
- `wrangler d1 execute` with `--file` runs the entire file in one transaction per batch — large files may hit the 10-second limit.
- The REST export API is **asynchronous** — you must poll with the bookmark until `status === 'complete'`.
- SQLite binary files (`.sqlite`) cannot be imported directly into D1 — convert to SQL dump first.
- Exporting large tables can take minutes; avoid doing this in a live Worker request.
- `--remote` flag is required to target the production database; omit it to use the local Wrangler dev database.
- Table names with special characters must be quoted in SQL: `"my-table"`.

## Related
- `d1-best-practices.md`
- `d1-migration-best-practices.md`
- `d1-time-travel.md`
