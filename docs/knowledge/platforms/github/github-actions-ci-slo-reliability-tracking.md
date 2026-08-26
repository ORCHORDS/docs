# GitHub Actions CI SLO and Reliability Tracking

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your example project monorepo CI pipeline runs dozens of workflows. You need to answer:
"What percentage of CI runs on `main` succeed? What is our median and P95 build
time? Which workflow is the most frequent source of failures?" Right now the only
answers come from squinting at the Actions tab. You want automated SLO tracking,
a dashboard, and Slack alerts when error-budget burn rate exceeds a threshold.

---

## Context

GitHub does not expose built-in SLO dashboards. You can construct them by
polling the Actions API and writing metrics to a store (D1, R2, or an external
TSDB). The core metrics are:

| Metric | Formula |
|--------|---------|
| Success rate | successful_runs / total_runs × 100 |
| MTTR | avg time from first failure to next success on same branch |
| Build duration P50 / P95 | percentile over `run.updated_at - run.created_at` |
| Error budget remaining | (1 − SLO_target) × window_hours − actual_downtime_hours |

A practical SLO for a monorepo CI main branch: **≥ 95% green on `main` over a
rolling 7-day window**.

---

## Data Collection — Scheduled Worker

```typescript
// workers/ci-metrics-collector/src/index.ts
import { Octokit } from "@octokit/rest";

export interface Env {
  GITHUB_TOKEN: string;      // Fine-grained PAT: Actions read
  DB: D1Database;
  REPO_OWNER: string;        // e.g. "your-org"
  REPO_NAME: string;         // e.g. "example project-monorepo"
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const octokit = new Octokit({ auth: env.GITHUB_TOKEN });

    // Collect runs from the last 2 hours (overlap prevents gaps)
    const since = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();

    const runs: WorkflowRun[] = [];
    for await (const page of octokit.paginate.iterator(
      octokit.rest.actions.listWorkflowRunsForRepo,
      {
        owner: env.REPO_OWNER,
        repo: env.REPO_NAME,
        created: `>=${since}`,
        per_page: 100,
      }
    )) {
      runs.push(...page.data);
    }

    // Upsert into D1
    const stmt = env.DB.prepare(`
      INSERT INTO ci_runs (
        run_id, workflow_name, branch, status, conclusion,
        created_at, updated_at, duration_seconds, actor
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(run_id) DO UPDATE SET
        status = excluded.status,
        conclusion = excluded.conclusion,
        updated_at = excluded.updated_at,
        duration_seconds = excluded.duration_seconds
    `);

    await env.DB.batch(
      runs.map((r) =>
        stmt.bind(
          r.id,
          r.name ?? r.workflow_id.toString(),
          r.head_branch ?? "unknown",
          r.status,
          r.conclusion ?? null,
          r.created_at,
          r.updated_at,
          Math.round(
            (new Date(r.updated_at).getTime() -
              new Date(r.created_at).getTime()) /
              1000
          ),
          r.actor?.login ?? "unknown"
        )
      )
    );

    console.log(`Upserted ${runs.length} CI runs`);
  },
} satisfies ExportedHandler<Env>;

interface WorkflowRun {
  id: number;
  name?: string | null;
  workflow_id: number;
  head_branch?: string | null;
  status: string;
  conclusion?: string | null;
  created_at: string;
  updated_at: string;
  actor?: { login: string } | null;
}
```

---

## D1 Schema

```sql
-- migrations/0010_ci_metrics.sql
CREATE TABLE IF NOT EXISTS ci_runs (
  run_id          INTEGER PRIMARY KEY,
  workflow_name   TEXT    NOT NULL,
  branch          TEXT    NOT NULL,
  status          TEXT    NOT NULL,   -- queued | in_progress | completed
  conclusion      TEXT,               -- success | failure | cancelled | skipped | timed_out
  created_at      TEXT    NOT NULL,
  updated_at      TEXT    NOT NULL,
  duration_seconds INTEGER,
  actor           TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ci_runs_branch_created
  ON ci_runs (branch, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ci_runs_workflow_conclusion
  ON ci_runs (workflow_name, conclusion, created_at DESC);
```

---

## SLO Query — 7-day Success Rate

```sql
-- Run via wrangler d1 execute or from a Worker
SELECT
  workflow_name,
  COUNT(*)                                            AS total,
  SUM(CASE WHEN conclusion = 'success' THEN 1 ELSE 0 END) AS passed,
  ROUND(
    100.0 * SUM(CASE WHEN conclusion = 'success' THEN 1 ELSE 0 END)
    / COUNT(*),
    2
  )                                                   AS success_pct,
  ROUND(AVG(duration_seconds) / 60.0, 1)             AS avg_minutes,
  -- Approximate P95 using subquery (D1 lacks PERCENTILE_CONT)
  (
    SELECT duration_seconds
    FROM ci_runs r2
    WHERE r2.workflow_name = r1.workflow_name
      AND r2.branch = 'main'
      AND r2.conclusion IS NOT NULL
      AND r2.created_at >= datetime('now', '-7 days')
    ORDER BY duration_seconds
    LIMIT 1
    OFFSET CAST(0.95 * COUNT(*) AS INTEGER)
  )                                                   AS p95_seconds
FROM ci_runs r1
WHERE branch = 'main'
  AND conclusion IS NOT NULL
  AND created_at >= datetime('now', '-7 days')
GROUP BY workflow_name
ORDER BY success_pct ASC;
```

---

## Error Budget Alert — GitHub Actions Cron

```yaml
# .github/workflows/ci-slo-check.yml
name: CI SLO Check

on:
  schedule:
    - cron: "0 * * * *"    # hourly
  workflow_dispatch:

permissions:
  contents: read

jobs:
  check-slo:
    name: Check CI Error Budget
    runs-on: ubuntu-24.04
    env:
      SLO_TARGET: "95"       # percent
      WINDOW_DAYS: "7"
      CF_ACCOUNT_ID: ${{ vars.CF_ACCOUNT_ID }}
      CF_API_TOKEN: ${{ secrets.CF_D1_READ_TOKEN }}
      D1_DATABASE_ID: ${{ vars.CI_METRICS_DB_ID }}

    steps:
      - name: Query SLO from D1
        id: slo
        run: |
          RESULT=$(curl -fsSL \
            "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/d1/database/${D1_DATABASE_ID}/query" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            -d '{
              "sql": "SELECT ROUND(100.0 * SUM(CASE WHEN conclusion = '\''success'\'' THEN 1 ELSE 0 END) / COUNT(*), 2) AS success_pct FROM ci_runs WHERE branch = '\''main'\'' AND conclusion IS NOT NULL AND created_at >= datetime('\''now'\'', '\''-7 days'\'')",
              "params": []
            }')

          SUCCESS_PCT=$(echo "$RESULT" | jq -r '.result[0].results[0].success_pct // "0"')
          echo "success_pct=${SUCCESS_PCT}" >> "$GITHUB_OUTPUT"
          echo "### CI SLO Result" >> "$GITHUB_STEP_SUMMARY"
          echo "7-day success rate on \`main\`: **${SUCCESS_PCT}%** (target: ${SLO_TARGET}%)" >> "$GITHUB_STEP_SUMMARY"

      - name: Alert if below SLO
        if: ${{ steps.slo.outputs.success_pct < env.SLO_TARGET }}
        env:
          SLACK_WEBHOOK: ${{ secrets.SLACK_ENGINEERING_WEBHOOK }}
          SUCCESS_PCT: ${{ steps.slo.outputs.success_pct }}
        run: |
          BUDGET_USED=$(echo "scale=1; (${SLO_TARGET} - ${SUCCESS_PCT}) * 7 * 24 / (100 - ${SLO_TARGET})" | bc)
          curl -fsSL -X POST "$SLACK_WEBHOOK" \
            -H 'Content-Type: application/json' \
            -d "$(jq -n \
              --arg pct "$SUCCESS_PCT" \
              --arg budget "$BUDGET_USED" \
              --arg repo "$GITHUB_REPOSITORY" \
              '{
                text: (":fire: *CI SLO Breach* for `" + $repo + "`\n" +
                       "7-day success rate: " + $pct + "% (below 95% target)\n" +
                       "Estimated error budget consumed: " + $budget + " hours\n" +
                       "Investigate: https://github.com/" + $repo + "/actions")
              }')"
```

---

## MTTR Calculation

Mean time to recovery (how long the branch stays red after a failure):

```sql
-- Pair each failure with the next success on the same workflow + branch
WITH ordered AS (
  SELECT
    workflow_name,
    branch,
    conclusion,
    created_at,
    LEAD(created_at) OVER (
      PARTITION BY workflow_name, branch
      ORDER BY created_at
    ) AS next_run_at,
    LEAD(conclusion) OVER (
      PARTITION BY workflow_name, branch
      ORDER BY created_at
    ) AS next_conclusion
  FROM ci_runs
  WHERE branch = 'main'
    AND conclusion IN ('failure', 'success')
    AND created_at >= datetime('now', '-30 days')
)
SELECT
  workflow_name,
  ROUND(AVG(
    (julianday(next_run_at) - julianday(created_at)) * 24 * 60
  ), 1) AS avg_mttr_minutes
FROM ordered
WHERE conclusion = 'failure'
  AND next_conclusion = 'success'
GROUP BY workflow_name
ORDER BY avg_mttr_minutes DESC;
```

---

## Job Summary Dashboard

Write a Markdown table to the step summary on each hourly run:

```yaml
- name: Write summary dashboard
  run: |
    echo "## CI Health Dashboard — $(date -u +%Y-%m-%d)" >> "$GITHUB_STEP_SUMMARY"
    echo "" >> "$GITHUB_STEP_SUMMARY"
    echo "| Workflow | 7d Success % | Avg Duration | Status |" >> "$GITHUB_STEP_SUMMARY"
    echo "|----------|-------------|--------------|--------|" >> "$GITHUB_STEP_SUMMARY"
    # (populate rows from D1 query output stored in prior step)
    echo "$ROWS" >> "$GITHUB_STEP_SUMMARY"
```

---

## Anti-patterns

- **Measuring SLO from the Actions UI page manually**: it resets on scroll and
  has no export. Always automate data collection.
- **Using workflow `conclusion: cancelled` in failure rate calculations**:
  cancelled runs (e.g. from concurrency groups) skew the success rate downward.
  Filter to `conclusion IN ('success', 'failure', 'timed_out')` for SLO math.
- **Setting SLO targets without a burn-rate window**: a single failure on a slow
  day can look catastrophic and a cluster of failures on a busy day can look
  minor. Always normalise by volume.
- **Alerting on every individual failure**: alert on the SLO breach rate, not on
  each flap. Reserve Slack pings for budget threshold crossings.
- **Storing raw GitHub API responses in D1**: the response objects are large and
  contain many fields you will never query. Extract only the columns you need.

---

## Gotchas

- The `updated_at` timestamp on a completed workflow run is the completion time,
  not the time the last step finished; there is a small discrepancy (~1s) due to
  API propagation. It is accurate enough for minute-level duration calculations.
- GitHub rate-limits the `listWorkflowRunsForRepo` endpoint to **1,000 requests
  per hour** for a PAT. A repo with 5,000 runs/day needs paginated collection
  across multiple scheduled jobs or a webhook-based approach.
- D1 does not support `PERCENTILE_CONT`. The subquery P95 approximation in the
  SLO query is slightly inaccurate for small sample sizes (<20 runs). Accept the
  approximation or export to R2 and use a proper TSDB for precise percentiles.
- `github.event.workflow_run` is available as an event trigger but only fires
  for workflows in the same repo. If you use cross-repo workflows, collect via
  API polling instead.

---

## Verification

```bash
# Check collector Worker is running on schedule
wrangler tail --name ci-metrics-collector

# Query current SLO
wrangler d1 execute ci-metrics \
  --command "SELECT workflow_name, success_pct FROM ci_slo_view ORDER BY success_pct ASC LIMIT 10"

# Manually trigger the SLO check alert workflow
gh workflow run ci-slo-check.yml --ref main
```

---

## Related

- `github-actions-job-summaries-wrangler-deploy-report.md`
- `github-actions-scheduled-cron-workers-maintenance.md`
- `github-actions-notify-slack.md`
- `github-deployment-api-workers-status-tracking.md`

---

## Sources

- GitHub REST API — List workflow runs: https://docs.github.com/en/rest/actions/workflow-runs
- Google SRE Book — Error budgets: https://sre.google/sre-book/embracing-risk/
- Cloudflare D1 Docs — Query API: https://developers.cloudflare.com/d1/worker-api/
- GitHub Actions — Workflow run event: https://docs.github.com/en/actions/using-workflows/events-that-trigger-workflows#workflow_run
