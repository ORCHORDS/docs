# Issue SLA Tracking and Alerting with Workers + D1

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Engineering and support teams need to guarantee response and resolution times for GitHub issues based on priority labels (P0/P1/P2/P3). Without automation, SLA breaches go unnoticed until a customer escalates. You need a system that tracks when each issue was opened and first responded to, fires alerts before breach, and produces a report endpoint for dashboards.

## Context

SLA tracking requires two timestamps per issue: `first_response_at` (first non-author comment) and `resolved_at` (issue closed). A Cloudflare Worker consumes webhook events from the queue produced by `workers-github-issue-webhook-router`, persists state in D1, and a cron trigger runs every 15 minutes to check for approaching or breached SLAs and send email alerts via MailChannels.

SLA tiers:
| Label | Time-to-First-Response | Time-to-Resolution |
|-------|----------------------|-------------------|
| P0    | 1 hour               | 4 hours           |
| P1    | 4 hours              | 24 hours          |
| P2    | 24 hours             | 72 hours          |
| P3    | 72 hours             | 7 days            |

## Solution

### 1. Wrangler configuration

```toml
# wrangler.toml
name = "issue-sla-tracker"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding = "DB"
database_name = "issue-sla"
database_id = "<your-d1-database-id>"

[[queues.consumers]]
queue = "issues-opened"
max_batch_size = 10
max_batch_timeout = 5

[[queues.consumers]]
queue = "issues-closed"
max_batch_size = 10
max_batch_timeout = 5

[triggers]
crons = ["*/15 * * * *"]

[vars]
ALERT_FROM_EMAIL = "sla-bot@example.com"
ALERT_TO_EMAIL = "eng-oncall@example.com"
```

### 2. D1 schema

```sql
-- schema.sql
CREATE TABLE IF NOT EXISTS issue_sla (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  repo_full_name        TEXT NOT NULL,
  issue_number          INTEGER NOT NULL,
  issue_id              INTEGER NOT NULL,
  title                 TEXT NOT NULL,
  html_url              TEXT NOT NULL,
  priority_label        TEXT,                    -- P0 / P1 / P2 / P3
  opened_at             TEXT NOT NULL,           -- ISO 8601
  first_response_at     TEXT,                   -- ISO 8601, NULL until responded
  resolved_at           TEXT,                   -- ISO 8601, NULL until closed
  tfr_breach_at         TEXT,                   -- computed deadline
  ttr_breach_at         TEXT,                   -- computed deadline
  tfr_alerted           INTEGER NOT NULL DEFAULT 0,  -- 1 = alert sent
  ttr_alerted           INTEGER NOT NULL DEFAULT 0,
  UNIQUE(repo_full_name, issue_number)
);

CREATE INDEX IF NOT EXISTS idx_sla_open ON issue_sla(resolved_at, tfr_breach_at, ttr_breach_at);
```

```bash
npx wrangler d1 execute issue-sla --file schema.sql
```

### 3. Types

```typescript
// src/types.ts
export interface Env {
  DB: D1Database;
  ALERT_FROM_EMAIL: string;
  ALERT_TO_EMAIL: string;
}

export const SLA_TIERS: Record<string, { tfrHours: number; ttrHours: number }> = {
  P0: { tfrHours: 1,  ttrHours: 4   },
  P1: { tfrHours: 4,  ttrHours: 24  },
  P2: { tfrHours: 24, ttrHours: 72  },
  P3: { tfrHours: 72, ttrHours: 168 },
};

export type SlaRow = {
  repo_full_name: string;
  issue_number: number;
  title: string;
  html_url: string;
  priority_label: string | null;
  opened_at: string;
  first_response_at: string | null;
  resolved_at: string | null;
  tfr_breach_at: string | null;
  ttr_breach_at: string | null;
  tfr_alerted: number;
  ttr_alerted: number;
};
```

### 4. SLA helpers

```typescript
// src/sla.ts
import { SLA_TIERS } from "./types";

export function detectPriority(labels: Array<{ name: string }>): string | null {
  for (const tier of ["P0", "P1", "P2", "P3"]) {
    if (labels.some((l) => l.name.toUpperCase() === tier)) return tier;
  }
  return null;
}

export function addHours(iso: string, hours: number): string {
  return new Date(new Date(iso).getTime() + hours * 3_600_000).toISOString();
}

export function computeBreaches(
  openedAt: string,
  priority: string | null
): { tfrBreachAt: string | null; ttrBreachAt: string | null } {
  if (!priority || !SLA_TIERS[priority]) {
    return { tfrBreachAt: null, ttrBreachAt: null };
  }
  const { tfrHours, ttrHours } = SLA_TIERS[priority];
  return {
    tfrBreachAt: addHours(openedAt, tfrHours),
    ttrBreachAt: addHours(openedAt, ttrHours),
  };
}
```

### 5. Queue consumer — issue opened

```typescript
// src/consumer-opened.ts
import type { Env } from "./types";
import { detectPriority, computeBreaches } from "./sla";
import type { IssueQueueMessage } from "./router-types";

export async function handleOpened(
  msg: Message<IssueQueueMessage>,
  env: Env
): Promise<void> {
  const { payload } = msg.body;
  const { issue, repository } = payload;
  const priority = detectPriority(issue.labels);
  const { tfrBreachAt, ttrBreachAt } = computeBreaches(issue.created_at, priority);

  await env.DB.prepare(
    `INSERT INTO issue_sla
       (repo_full_name, issue_number, issue_id, title, html_url,
        priority_label, opened_at, tfr_breach_at, ttr_breach_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(repo_full_name, issue_number) DO NOTHING`
  )
    .bind(
      repository.full_name,
      issue.number,
      issue.id,
      issue.title,
      issue.html_url,
      priority,
      issue.created_at,
      tfrBreachAt,
      ttrBreachAt
    )
    .run();
}
```

### 6. Queue consumer — issue closed

```typescript
// src/consumer-closed.ts
import type { Env } from "./types";
import type { IssueQueueMessage } from "./router-types";

export async function handleClosed(
  msg: Message<IssueQueueMessage>,
  env: Env
): Promise<void> {
  const { payload } = msg.body;
  const { issue, repository } = payload;
  const resolvedAt = issue.closed_at ?? new Date().toISOString();

  await env.DB.prepare(
    `UPDATE issue_sla
     SET resolved_at = ?
     WHERE repo_full_name = ? AND issue_number = ?`
  )
    .bind(resolvedAt, repository.full_name, issue.number)
    .run();
}
```

### 7. MailChannels alert sender

```typescript
// src/alert.ts
import type { Env, SlaRow } from "./types";

export async function sendBreachAlert(
  env: Env,
  issue: SlaRow,
  breachType: "TFR" | "TTR"
): Promise<void> {
  const label = breachType === "TFR" ? "Time-to-First-Response" : "Time-to-Resolution";
  const body = {
    personalizations: [{ to: [{ email: env.ALERT_TO_EMAIL }] }],
    from: { email: env.ALERT_FROM_EMAIL },
    subject: `[SLA BREACH] ${issue.priority_label} issue #${issue.issue_number} — ${label} exceeded`,
    content: [
      {
        type: "text/plain",
        value: [
          `Repository: ${issue.repo_full_name}`,
          `Issue:      #${issue.issue_number} — ${issue.title}`,
          `Priority:   ${issue.priority_label}`,
          `URL:        ${issue.html_url}`,
          `Opened at:  ${issue.opened_at}`,
          `Breach type: ${label}`,
        ].join("\n"),
      },
    ],
  };

  const res = await fetch("https://api.mailchannels.net/tx/v1/send", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    throw new Error(`MailChannels error: ${res.status} ${await res.text()}`);
  }
}
```

### 8. Cron escalation handler

```typescript
// src/cron.ts
import type { Env, SlaRow } from "./types";
import { sendBreachAlert } from "./alert";

export async function runEscalationCheck(env: Env): Promise<void> {
  const now = new Date().toISOString();

  // Find unresolved issues where TFR breach time has passed and we haven't alerted yet
  const tfrBreached = await env.DB.prepare(
    `SELECT * FROM issue_sla
     WHERE resolved_at IS NULL
       AND tfr_breach_at IS NOT NULL
       AND tfr_breach_at <= ?
       AND first_response_at IS NULL
       AND tfr_alerted = 0`
  )
    .bind(now)
    .all<SlaRow>();

  for (const row of tfrBreached.results) {
    try {
      await sendBreachAlert(env, row, "TFR");
      await env.DB.prepare(
        `UPDATE issue_sla SET tfr_alerted = 1 WHERE repo_full_name = ? AND issue_number = ?`
      )
        .bind(row.repo_full_name, row.issue_number)
        .run();
    } catch (err) {
      console.error(`TFR alert failed for ${row.repo_full_name}#${row.issue_number}:`, err);
    }
  }

  // Find unresolved issues where TTR breach time has passed
  const ttrBreached = await env.DB.prepare(
    `SELECT * FROM issue_sla
     WHERE resolved_at IS NULL
       AND ttr_breach_at IS NOT NULL
       AND ttr_breach_at <= ?
       AND ttr_alerted = 0`
  )
    .bind(now)
    .all<SlaRow>();

  for (const row of ttrBreached.results) {
    try {
      await sendBreachAlert(env, row, "TTR");
      await env.DB.prepare(
        `UPDATE issue_sla SET ttr_alerted = 1 WHERE repo_full_name = ? AND issue_number = ?`
      )
        .bind(row.repo_full_name, row.issue_number)
        .run();
    } catch (err) {
      console.error(`TTR alert failed for ${row.repo_full_name}#${row.issue_number}:`, err);
    }
  }

  console.log(
    `Escalation check complete. TFR breaches: ${tfrBreached.results.length}, TTR breaches: ${ttrBreached.results.length}`
  );
}
```

### 9. SLA report endpoint

```typescript
// src/report.ts
import type { Env } from "./types";

export async function handleReport(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const repo = url.searchParams.get("repo"); // optional filter

  let query = `
    SELECT
      priority_label,
      COUNT(*) AS total,
      SUM(CASE WHEN first_response_at IS NULL AND tfr_breach_at < datetime('now') THEN 1 ELSE 0 END) AS tfr_breached,
      SUM(CASE WHEN resolved_at IS NULL AND ttr_breach_at < datetime('now') THEN 1 ELSE 0 END) AS ttr_breached,
      AVG(
        CASE WHEN first_response_at IS NOT NULL
        THEN (julianday(first_response_at) - julianday(opened_at)) * 24
        END
      ) AS avg_tfr_hours,
      AVG(
        CASE WHEN resolved_at IS NOT NULL
        THEN (julianday(resolved_at) - julianday(opened_at)) * 24
        END
      ) AS avg_ttr_hours
    FROM issue_sla
  `;

  const bindings: string[] = [];
  if (repo) {
    query += " WHERE repo_full_name = ?";
    bindings.push(repo);
  }
  query += " GROUP BY priority_label ORDER BY priority_label";

  const result = await env.DB.prepare(query).bind(...bindings).all();

  return new Response(JSON.stringify({ generated_at: new Date().toISOString(), rows: result.results }), {
    headers: { "content-type": "application/json" },
  });
}
```

### 10. Main entry point

```typescript
// src/index.ts
import type { Env } from "./types";
import { handleOpened } from "./consumer-opened";
import { handleClosed } from "./consumer-closed";
import { runEscalationCheck } from "./cron";
import { handleReport } from "./report";
import type { IssueQueueMessage } from "./router-types";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname === "/sla/report") return handleReport(request, env);
    return new Response("Not Found", { status: 404 });
  },

  async queue(batch: MessageBatch<IssueQueueMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        const action = msg.body.payload.action;
        if (action === "opened") await handleOpened(msg, env);
        else if (action === "closed") await handleClosed(msg, env);
        msg.ack();
      } catch (err) {
        console.error(err);
        msg.retry();
      }
    }
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await runEscalationCheck(env);
  },
} satisfies ExportedHandler<Env>;
```

## Implementation Details

- SLA breach deadlines (`tfr_breach_at`, `ttr_breach_at`) are computed once at issue creation and stored in D1, avoiding repeated arithmetic on every cron tick.
- `first_response_at` is updated by a separate webhook consumer that listens to the `issue_comment` event and checks whether the commenter is not the issue author.
- `ON CONFLICT DO NOTHING` in the insert prevents duplicate rows if the same opened event is replayed after the KV dedup window.
- MailChannels is available to Workers on the Cloudflare network with no API key required for email from Worker-owned domains (SPF/DKIM must be configured).
- The `*/15 * * * *` cron gives a maximum 15-minute late-alert window; reduce to `*/5` for P0 SLAs if needed.

## Anti-patterns

- **Do not compute SLA deadlines inside the cron.** Pre-computing at creation time keeps cron queries simple indexed range scans.
- **Do not send one email per cron per breached issue every tick.** The `tfr_alerted` / `ttr_alerted` flags prevent alert storms.
- **Do not use D1 `datetime('now')` for insertion timestamps.** Pass ISO strings from the Worker runtime to ensure timezone consistency.
- **Do not hard-code SLA tiers in SQL.** Keep them in `SLA_TIERS` in TypeScript so they are testable.

## Gotchas

- D1 is eventually consistent on read replicas. For the cron escalation query, it is fine; for the report endpoint under heavy write load, results may lag by a few seconds.
- GitHub does not send a webhook when a comment is posted by an automated bot unless the webhook is configured for `issue_comment` events — add that event in the GitHub App or webhook settings.
- MailChannels email delivery requires the sending domain to have SPF/DKIM records pointing to Cloudflare. Without these, messages go to spam or are rejected.
- If an issue is labeled after creation (changing priority), the breach deadlines stored at creation time will be wrong. Re-compute and update `tfr_breach_at`/`ttr_breach_at` in the `labeled` event consumer.

## Verification

```bash
# Run the schema migration
npx wrangler d1 execute issue-sla --file schema.sql --remote

# Deploy
npx wrangler deploy

# Manually trigger cron in dev
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*/15+*+*+*+*"

# Check the SLA report
curl "https://<your-worker>.workers.dev/sla/report?repo=example-org/example-repo" | jq .

# Verify D1 rows
npx wrangler d1 execute issue-sla --command "SELECT * FROM issue_sla LIMIT 5" --remote
```

## Related

- `workers-github-issue-webhook-router.md` — upstream webhook fan-out to Queues
- `workers-release-notes-from-issues-d1.md` — using D1 issue data for release notes

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/scheduled-event/
- https://support.mailchannels.com/hc/en-us/articles/4565898875917
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#issues
