# Stripe Sigma Scheduled Exports into D1 for Analytics

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You need queryable historical payment analytics (cohort revenue, churn, LTV) but Stripe Sigma
runs only within Stripe's dashboard and doesn't feed external BI tools; you want the raw CSV
export files landing in D1 so you can JOIN them against your own user table.

## Context
Stripe's Scheduled Exports (Data Management → Scheduled Exports in the Dashboard, or via
the `reporting.report_run` API) produce GZIP-compressed CSVs posted to a signed S3-compatible
URL. A Cloudflare Cron Trigger fires a Worker that polls `reporting.report_run` for completed
runs, downloads the CSV through the signed URL (which works from Worker egress IPs), parses
it with a streaming CSV reader, and bulk-inserts rows into D1 in batches of 100 using
prepared statements.

---

## Scheduling a Report Run via the API

Create a `balance_transaction` report run nightly; the Worker logs the `run_id` in D1 so the
next invocation knows which runs are already ingested.

```typescript
// src/schedule-report.ts
export interface Env {
  STRIPE_SECRET_KEY: string;
  DB: D1Database;
}

export async function createReportRun(
  reportType: string,
  intervalStartSeconds: number,
  intervalEndSeconds: number,
  env: Env
): Promise<string> {
  const body = new URLSearchParams({
    report_type: reportType,
    'parameters[interval_start]': String(intervalStartSeconds),
    'parameters[interval_end]': String(intervalEndSeconds),
    'parameters[timezone]': 'UTC',
  });

  const res = await fetch('https://api.stripe.com/v1/reporting/report_runs', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Content-Type': 'application/x-www-form-urlencoded',
      'Stripe-Version': '2024-06-20',
    },
    body,
  });

  if (!res.ok) {
    const err = await res.json<{ error: { message: string } }>();
    throw new Error(`Report run creation failed: ${err.error.message}`);
  }

  const run = await res.json<{ id: string }>();

  await env.DB.prepare(
    `INSERT OR IGNORE INTO stripe_report_runs (run_id, report_type, interval_start, interval_end, status, created_at)
     VALUES (?, ?, ?, ?, 'pending', unixepoch())`
  )
    .bind(run.id, reportType, intervalStartSeconds, intervalEndSeconds)
    .run();

  return run.id;
}
```

## Polling for Completion and Downloading the CSV

Stripe report runs typically complete within 5–30 minutes. The Cron handler polls pending runs
and downloads the file when `status === 'succeeded'`.

```typescript
// src/ingest.ts
interface ReportRun {
  id: string;
  status: 'pending' | 'succeeded' | 'failed';
  result?: { url: string };
}

export async function pollAndIngest(env: Env): Promise<void> {
  const pending = await env.DB.prepare(
    `SELECT run_id FROM stripe_report_runs WHERE status = 'pending' LIMIT 10`
  ).all<{ run_id: string }>();

  for (const { run_id } of pending.results) {
    const res = await fetch(
      `https://api.stripe.com/v1/reporting/report_runs/${run_id}`,
      {
        headers: {
          Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
          'Stripe-Version': '2024-06-20',
        },
      }
    );
    const run = await res.json<ReportRun>();

    if (run.status === 'failed') {
      await env.DB.prepare(
        `UPDATE stripe_report_runs SET status = 'failed' WHERE run_id = ?`
      )
        .bind(run_id)
        .run();
      continue;
    }

    if (run.status !== 'succeeded' || !run.result?.url) continue;

    // Signed URL — fetch directly from Worker egress
    const csvRes = await fetch(run.result.url);
    if (!csvRes.ok) throw new Error(`CSV download failed for ${run_id}`);

    const csvText = await csvRes.text();
    await ingestCsv(csvText, run_id, env);

    await env.DB.prepare(
      `UPDATE stripe_report_runs SET status = 'ingested', ingested_at = unixepoch() WHERE run_id = ?`
    )
      .bind(run_id)
      .run();
  }
}
```

## Bulk CSV Insert into D1

Parse rows with a minimal CSV splitter and insert in batches of 100 using `DB.batch()`.

```typescript
// src/csv-insert.ts
function parseCsvRows(csv: string): Record<string, string>[] {
  const lines = csv.replace(/\r\n/g, '\n').split('\n');
  const headers = lines[0].split(',').map((h) => h.trim().replace(/^"|"$/g, ''));
  return lines
    .slice(1)
    .filter(Boolean)
    .map((line) => {
      const values = line.split(',').map((v) => v.trim().replace(/^"|"$/g, ''));
      return Object.fromEntries(headers.map((h, i) => [h, values[i] ?? '']));
    });
}

export async function ingestCsv(
  csv: string,
  runId: string,
  env: Env
): Promise<void> {
  const rows = parseCsvRows(csv);
  const BATCH = 100;

  for (let i = 0; i < rows.length; i += BATCH) {
    const chunk = rows.slice(i, i + BATCH);
    const stmts = chunk.map((row) =>
      env.DB.prepare(
        `INSERT OR IGNORE INTO stripe_balance_transactions
           (id, created, amount, currency, type, description, run_id)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        row['id'] ?? '',
        row['created'] ?? '',
        Number(row['amount'] ?? 0),
        row['currency'] ?? '',
        row['type'] ?? '',
        row['description'] ?? '',
        runId
      )
    );
    await env.DB.batch(stmts);
  }
}

// D1 schema (run once via wrangler d1 execute)
// CREATE TABLE IF NOT EXISTS stripe_balance_transactions (
//   id TEXT PRIMARY KEY,
//   created TEXT,
//   amount INTEGER,
//   currency TEXT,
//   type TEXT,
//   description TEXT,
//   run_id TEXT,
//   FOREIGN KEY (run_id) REFERENCES stripe_report_runs(run_id)
// );
// CREATE TABLE IF NOT EXISTS stripe_report_runs (
//   run_id TEXT PRIMARY KEY,
//   report_type TEXT,
//   interval_start INTEGER,
//   interval_end INTEGER,
//   status TEXT,
//   created_at INTEGER,
//   ingested_at INTEGER
// );
```

## Anti-patterns
- Storing the raw CSV in KV — blobs over 25 MB will exceed KV value limits; stream directly
  to D1 insert batches.
- Fetching the signed URL more than once — Stripe's signed S3 URLs are single-use for some
  report types; download once, parse in memory.
- Re-running the entire ETL on every cron tick — always track `run_id` state in D1 and skip
  already-ingested runs.
- Using `INSERT` without `OR IGNORE` — duplicate run ingestion on retry will cause PK
  conflicts and silently abort the entire batch statement.

## Gotchas
- Stripe report runs for large accounts can produce multiple files; the `result.url` in the
  run object is always a single GZIP file, but the CSV can be hundreds of MB — stream-parse
  rather than holding the full string in memory for large volumes.
- The signed URL expires (typically 60 seconds); fetch it immediately after detecting
  `status === 'succeeded'`, not in a deferred queue.
- Column names in Sigma CSV exports change between Stripe API versions — pin
  `Stripe-Version` and test after Stripe API upgrades.
- Workers have a 128 MB memory limit — for exports exceeding ~50 MB uncompressed, split
  ingestion across multiple Cron invocations using a `row_offset` cursor stored in D1.

## Verification
```sql
-- Check ingestion status
SELECT status, COUNT(*) FROM stripe_report_runs GROUP BY status;

-- Spot-check ingested transactions
SELECT id, created, amount / 100.0 AS amount_usd, type
FROM stripe_balance_transactions
ORDER BY created DESC
LIMIT 20;

-- Revenue by day
SELECT substr(created, 1, 10) AS day, SUM(amount) / 100.0 AS revenue_usd
FROM stripe_balance_transactions
WHERE type = 'charge'
GROUP BY day
ORDER BY day DESC;
```

```bash
# Trigger a manual cron run
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=0+4+*+*+*"
```

## Related
- `stripe-sigma-custom-reports.md`
- `payment-analytics-cohort-retention-d1.md`
- `stripe-revenue-recognition-d1-reporting.md`
- `payment-reconciliation-settlement.md`

## Sources
- https://stripe.com/docs/reports/scheduled-exports
- https://stripe.com/docs/api/reporting/report_run
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://stripe.com/docs/reports/balance-transaction-types
