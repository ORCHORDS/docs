# Spam Filtering Inbound Email Using Workers + D1

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You receive unwanted mail from known spam senders or entire abusive domains and want to block them at the SMTP level, before the message hits any inbox. A D1-backed blocklist lets you maintain, query, and update the deny-list with SQL while the Cloudflare Email Worker rejects matching messages with a 550 during the SMTP conversation.

---

## Context

Cloudflare D1 is a serverless SQLite database accessible from Workers via the `DB` binding. Each inbound `EmailMessage` carries `message.from` (the RFC-5321 envelope sender). On every inbound message the Worker runs a parameterized D1 query against a `blocklist` table that stores individual addresses and domain wildcards. A match triggers `message.setReject("spam")`, which ends the SMTP session with a permanent failure code so the sending MTA does not retry. Blocked-send counts are incremented in D1 for reporting. Bulk import from a CSV file is handled via a Wrangler D1 SQL execution command.

---

## Section 1 — D1 Schema & Wrangler Config

```toml
# wrangler.toml
name = "email-spam-filter"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "email-blocklist"
database_id = "<YOUR_D1_DATABASE_ID>"
```

```sql
-- migrations/0001_blocklist.sql
CREATE TABLE IF NOT EXISTS blocklist (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entry       TEXT    NOT NULL UNIQUE,   -- email or @domain.com
  entry_type  TEXT    NOT NULL CHECK(entry_type IN ('address', 'domain')),
  blocked_count INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_blocklist_entry ON blocklist(entry);
```

```bash
# Create the database
npx wrangler d1 create email-blocklist

# Apply migration
npx wrangler d1 execute email-blocklist --file=migrations/0001_blocklist.sql
```

## Section 2 — Implementation

```typescript
// src/index.ts
export interface Env {
  DB: D1Database;
}

interface EmailMessage {
  readonly from: string;
  readonly to: string;
  readonly headers: Headers;
  readonly raw: ReadableStream;
  forward(rcptTo: string, headers?: Headers): Promise<void>;
  setReject(reason: string): void;
}

async function isBlocked(db: D1Database, from: string): Promise<boolean> {
  const lower = from.toLowerCase();
  const atIndex = lower.indexOf("@");
  const domain = atIndex >= 0 ? lower.slice(atIndex) : null; // e.g. "@spam.com"

  // Check exact address match or domain wildcard in one query
  const result = await db
    .prepare(
      `SELECT id FROM blocklist
       WHERE entry = ?1
          OR (entry_type = 'domain' AND entry = ?2)
       LIMIT 1`
    )
    .bind(lower, domain ?? "")
    .first<{ id: number }>();

  return result !== null;
}

async function incrementBlockCount(db: D1Database, from: string): Promise<void> {
  const lower = from.toLowerCase();
  const atIndex = lower.indexOf("@");
  const domain = atIndex >= 0 ? lower.slice(atIndex) : null;

  await db
    .prepare(
      `UPDATE blocklist
       SET blocked_count = blocked_count + 1
       WHERE entry = ?1
          OR (entry_type = 'domain' AND entry = ?2)`
    )
    .bind(lower, domain ?? "")
    .run();
}

export default {
  async email(message: EmailMessage, env: Env, _ctx: ExecutionContext): Promise<void> {
    const blocked = await isBlocked(env.DB, message.from);

    if (blocked) {
      // Fire-and-forget increment — rejection does not need to wait for it
      _ctx.waitUntil(incrementBlockCount(env.DB, message.from));
      message.setReject("spam");
      return;
    }

    // Pass through to the configured Email Routing destination
    await message.forward("inbox@example.com");
  },
};
```

## Section 3 — Bulk Import from CSV via Wrangler

```bash
# blocklist.csv format:
# entry,entry_type
# spammer@evil.com,address
# @bulk-spam-domain.net,domain

# Convert CSV to SQL INSERT statements
python3 - <<'PY'
import csv, sys
print("BEGIN TRANSACTION;")
with open("blocklist.csv") as f:
    for row in csv.DictReader(f):
        entry = row["entry"].strip().lower().replace("'", "''")
        etype = row["entry_type"].strip()
        print(f"INSERT OR IGNORE INTO blocklist(entry, entry_type) VALUES ('{entry}', '{etype}');")
print("COMMIT;")
PY > blocklist_import.sql

# Execute in D1
npx wrangler d1 execute email-blocklist --file=blocklist_import.sql

# Verify row count
npx wrangler d1 execute email-blocklist \
  --command="SELECT COUNT(*) as total FROM blocklist;"
```

---

## Anti-patterns

- **Storing full regexes in D1 and evaluating in Worker** — Regex matching in the Worker hot path adds latency; use structured `entry_type` values (`address`/`domain`) and let SQLite's indexed lookup do the work.
- **Not using `ctx.waitUntil` for the increment** — Awaiting the UPDATE before `setReject` adds unnecessary latency to the SMTP rejection path; move it to `waitUntil` so the response is immediate.
- **Case-sensitive comparisons** — Email addresses are technically case-insensitive in the local part (per RFC); always lowercase both the stored entry and `message.from` before comparing.

---

## Gotchas

- `message.setReject()` must be called synchronously within the `email` handler — you cannot call it inside a `.then()` callback that runs after the handler returns.
- D1 in Workers has a 50 ms CPU time budget per request in the free tier; the single-query approach above keeps well within that.
- `database_id` in `wrangler.toml` must match exactly; a wrong ID causes a silent binding failure that surfaces as `env.DB is undefined` at runtime.
- Soft-blocking (allow but mark) requires forwarding the message anyway and setting a custom header; `setReject` is permanent for that SMTP session.

---

## Verification

```bash
# Query current blocklist
npx wrangler d1 execute email-blocklist \
  --command="SELECT entry, entry_type, blocked_count FROM blocklist ORDER BY blocked_count DESC LIMIT 20;"

# Tail live rejections
npx wrangler tail email-spam-filter --format=json \
  | jq 'select(.logs[].message | test("spam"; "i"))'

# Test rejection with swaks
swaks --to catch-all@yourdomain.com --from spammer@evil.com \
  --server mx1.yourdomain.com --quit-after RCPT
# Expected: 550 spam
```

---

## Related

- `workers-email-routing-forward-transform.md`
- `workers-email-bounce-webhook-handler.md`

---

## Sources

- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Email Workers Runtime API — https://developers.cloudflare.com/email-routing/email-workers/runtime-api/
- RFC 5321 case insensitivity — https://datatracker.ietf.org/doc/html/rfc5321#section-2.4
