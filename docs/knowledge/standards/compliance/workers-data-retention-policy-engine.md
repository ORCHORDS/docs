# Configurable Data Retention Policy Engine in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your application stores multiple categories of personal data (session logs, analytics events, consent records, payment references) each with a different legally mandated retention period. You need a single, centrally configured engine that enforces those periods automatically — deleting expired rows on a schedule — while writing an immutable audit log of every deletion for regulatory accountability.

---

## Context

Data retention is mandated by virtually every privacy regulation (GDPR Art. 5(1)(e), LGPD Art. 16, NDPR, PDPA) under the storage-limitation principle: personal data must not be kept longer than necessary. Different categories have different periods — for example, transaction records may be kept for 7 years for tax purposes while marketing consent records expire after the consent period ends. A single configurable D1 table (`retention_policies`) keyed by `data_category` avoids scattering retention logic across multiple Workers. A Cron trigger runs the purge on a nightly schedule and writes every deletion batch to a `deletion_log` table that is itself never deleted (or is retained for a longer fixed period as required by law).

---

## Section 1 — D1 Schema

```sql
-- retention_policies: one row per data category
CREATE TABLE IF NOT EXISTS retention_policies (
  data_category    TEXT PRIMARY KEY,       -- e.g. 'session_logs', 'consent_records'
  target_table     TEXT NOT NULL,          -- actual D1 table to purge
  retention_days   INTEGER NOT NULL,       -- how long to keep rows
  date_column      TEXT NOT NULL DEFAULT 'created_at',  -- column used for age check
  enabled          INTEGER NOT NULL DEFAULT 1,          -- 0 = paused
  description      TEXT,
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Pre-populate with common categories
INSERT OR IGNORE INTO retention_policies
  (data_category, target_table, retention_days, date_column, description)
VALUES
  ('session_logs',         'session_logs',         90,    'created_at', 'GDPR Art.5 storage limitation'),
  ('analytics_events',     'analytics_events',     365,   'event_time', 'Internal analytics retention'),
  ('consent_records',      'lgpd_consent',         1825,  'granted_at', '5-year consent evidence'),
  ('marketing_leads',      'marketing_leads',      730,   'captured_at','2-year max without re-consent'),
  ('breach_notifications', 'ndpr_breach_log',      2555,  'detected_at','7-year breach evidence');

-- deletion_log: immutable audit trail of all purge operations
CREATE TABLE IF NOT EXISTS deletion_log (
  id               TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  run_id           TEXT NOT NULL,          -- groups all deletions from one Cron run
  data_category    TEXT NOT NULL,
  target_table     TEXT NOT NULL,
  retention_days   INTEGER NOT NULL,
  cutoff_date      TEXT NOT NULL,
  rows_deleted     INTEGER NOT NULL,
  purged_at        TEXT NOT NULL DEFAULT (datetime('now')),
  triggered_by     TEXT NOT NULL DEFAULT 'cron'
);

CREATE INDEX IF NOT EXISTS idx_deletion_log_run  ON deletion_log(run_id);
CREATE INDEX IF NOT EXISTS idx_deletion_log_cat  ON deletion_log(data_category);
CREATE INDEX IF NOT EXISTS idx_deletion_log_date ON deletion_log(purged_at);
```

---

## Section 2 — Worker Policy Manager

```typescript
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
}

const app = new Hono<{ Bindings: Env }>();

// GET /retention/policies — list all configured retention policies
app.get('/retention/policies', async (c) => {
  const { results } = await c.env.DB.prepare(
    `SELECT data_category, target_table, retention_days, date_column,
            enabled, description, updated_at
     FROM retention_policies
     ORDER BY data_category`
  ).all();
  return c.json(results);
});

// PUT /retention/policies/:category — update retention period for a category
app.put('/retention/policies/:category', async (c) => {
  const category = c.req.param('category');
  const body = await c.req.json<{
    retention_days?: number;
    enabled?: boolean;
    description?: string;
  }>();

  const sets: string[] = [];
  const values: (string | number)[] = [];

  if (body.retention_days !== undefined) {
    sets.push('retention_days = ?');
    values.push(body.retention_days);
  }
  if (body.enabled !== undefined) {
    sets.push('enabled = ?');
    values.push(body.enabled ? 1 : 0);
  }
  if (body.description !== undefined) {
    sets.push('description = ?');
    values.push(body.description);
  }

  if (sets.length === 0) return c.json({ error: 'Nothing to update' }, 400);

  sets.push("updated_at = datetime('now')");
  values.push(category);

  const { meta } = await c.env.DB.prepare(
    `UPDATE retention_policies SET ${sets.join(', ')} WHERE data_category = ?`
  ).bind(...values).run();

  if (meta.changes === 0) return c.json({ error: 'Category not found' }, 404);
  return c.json({ status: 'updated' });
});

// POST /retention/policies — create a new retention policy
app.post('/retention/policies', async (c) => {
  const body = await c.req.json<{
    data_category: string;
    target_table: string;
    retention_days: number;
    date_column?: string;
    description?: string;
  }>();

  await c.env.DB.prepare(
    `INSERT INTO retention_policies
       (data_category, target_table, retention_days, date_column, description)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(
    body.data_category,
    body.target_table,
    body.retention_days,
    body.date_column ?? 'created_at',
    body.description ?? null
  ).run();

  return c.json({ status: 'created' }, 201);
});

export default app;
```

---

## Section 3 — Cron Purge Handler

```typescript
import type { Env } from './types';

type Policy = {
  data_category: string;
  target_table: string;
  retention_days: number;
  date_column: string;
};

/**
 * purgeExpiredData: runs as a Cron trigger (e.g. daily at 02:00 UTC).
 * Reads all enabled retention policies, deletes expired rows from each target
 * table, and records the operation in deletion_log.
 *
 * IMPORTANT: target_table and date_column are read from the database — never
 * from user input — to prevent SQL injection via policy manipulation.
 * Validate that both values match a known allowlist before interpolating.
 */
const TABLE_ALLOWLIST = new Set([
  'session_logs',
  'analytics_events',
  'lgpd_consent',
  'marketing_leads',
  'ndpr_breach_log',
  'pdpa_consents',
]);

const COLUMN_ALLOWLIST = new Set([
  'created_at',
  'granted_at',
  'event_time',
  'captured_at',
  'detected_at',
  'withdrawn_at',
]);

export async function purgeExpiredData(
  _event: ScheduledEvent,
  env: Env
): Promise<void> {
  const runId = crypto.randomUUID();
  const { results: policies } = await env.DB.prepare(
    `SELECT data_category, target_table, retention_days, date_column
     FROM retention_policies
     WHERE enabled = 1`
  ).all<Policy>();

  console.log(`[Retention] Run ${runId}: processing ${policies.length} policies`);

  for (const policy of policies) {
    // Allowlist check prevents SQL injection even if DB is compromised
    if (
      !TABLE_ALLOWLIST.has(policy.target_table) ||
      !COLUMN_ALLOWLIST.has(policy.date_column)
    ) {
      console.error(
        `[Retention] Skipping ${policy.data_category}: ` +
        `table/column not in allowlist`
      );
      continue;
    }

    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - policy.retention_days);
    const cutoffIso = cutoffDate.toISOString().slice(0, 19); // 'YYYY-MM-DDTHH:MM:SS'

    try {
      // Safe interpolation: both identifiers validated against allowlist above
      const { meta } = await env.DB.prepare(
        `DELETE FROM ${policy.target_table}
         WHERE ${policy.date_column} < ?`
      ).bind(cutoffIso).run();

      await env.DB.prepare(
        `INSERT INTO deletion_log
           (run_id, data_category, target_table, retention_days, cutoff_date, rows_deleted)
         VALUES (?, ?, ?, ?, ?, ?)`
      ).bind(
        runId,
        policy.data_category,
        policy.target_table,
        policy.retention_days,
        cutoffIso,
        meta.changes
      ).run();

      console.log(
        `[Retention] ${policy.data_category}: deleted ${
          meta.changes
        } rows older than ${cutoffIso}`
      );
    } catch (err) {
      console.error(
        `[Retention] Failed to purge ${policy.data_category}:`,
        (err as Error).message
      );
    }
  }

  console.log(`[Retention] Run ${runId} complete`);
}

// wrangler.toml excerpt:
// [triggers]
// crons = ["0 2 * * *"]  # nightly at 02:00 UTC
```

---

## Anti-patterns

- **Interpolating `target_table` from the database directly into SQL without allowlisting** — Even though the value comes from your own DB, a SSRF/injection attack or misconfiguration could set it to a harmful value. Always validate against a compile-time allowlist.
- **Deleting from the `deletion_log` table itself** — The deletion log is your audit evidence; it must be retained separately, typically for 7 years for most tax and privacy regulations. Do not include it in any retention policy.
- **Setting `retention_days = 0`** — This would delete all rows on every Cron run, including rows just inserted. Enforce a minimum of 1 day in the API handler.
- **Running the purge synchronously in a request handler** — Large DELETE operations can exceed the 30-second CPU limit; always run purges in Cron triggers, never in the request path.

---

## Gotchas

- D1's `DELETE` statement does not return deleted row content, only the count via `meta.changes`. If you need a record of *which* rows were deleted (for portability exports or audit), add an `archived_records` table and `INSERT … SELECT` before deleting.
- `datetime('now', '-N days')` in D1 is SQLite syntax; you can use it in the DELETE WHERE clause directly, but the approach above computes the cutoff in JavaScript for clarity and logging.
- Cron triggers fire at most once per trigger expression per Worker invocation; if a purge run exceeds the 30-second CPU time limit, it will be killed mid-run. Add a `LIMIT` clause (e.g. `DELETE … WHERE rowid IN (SELECT rowid FROM … LIMIT 10000)`) to batch large deletions.
- The `deletion_log` table will grow indefinitely. Consider a separate, longer retention policy enforced by a manual DBA process, not the engine itself.

---

## Verification

```bash
# Apply schema and seed policies
wrangler d1 execute retention-db --file=schema.sql

# List current policies
curl https://your-worker.dev/retention/policies

# Shorten session_logs retention to 30 days (for testing)
curl -X PUT https://your-worker.dev/retention/policies/session_logs \
  -H 'Content-Type: application/json' \
  -d '{"retention_days": 30}'

# Add a new policy
curl -X POST https://your-worker.dev/retention/policies \
  -H 'Content-Type: application/json' \
  -d '{"data_category":"chat_messages","target_table":"chat_messages",\
       "retention_days":180,"date_column":"created_at"}'

# Trigger Cron manually via Wrangler
wrangler triggers invoke --name=purge-cron

# Verify deletion_log
wrangler d1 execute retention-db \
  --command "SELECT data_category, rows_deleted, purged_at FROM deletion_log ORDER BY purged_at DESC LIMIT 20;"
```

---

## Related

- `brazil-lgpd-workers-d1-consent.md`
- `thailand-pdpa-workers-d1.md`
- `nigeria-ndpr-workers-d1.md`
- `workers-privacy-by-design-data-minimisation.md`

---

## Sources

- GDPR Art. 5(1)(e) — Storage limitation — https://gdpr-info.eu/art-5-gdpr/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- Cloudflare Workers Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
