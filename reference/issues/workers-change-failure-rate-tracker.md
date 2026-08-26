# Change Failure Rate Tracking for DORA Metrics

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your team wants to measure DORA's Change Failure Rate (CFR) — the percentage of deployments that cause a production incident — but the data lives in disconnected systems: GitHub deployment webhooks, PagerDuty alerts, and Jira. You need a Worker that ingests GitHub deployment events, links them to incidents in D1, computes CFR per time window, classifies your DORA tier, exposes a trend endpoint, and sends a weekly report.

## Context

CFR is defined as `failed_deployments / total_deployments` over a rolling window. "Failed" means a deployment was linked to an incident opened within a configurable window after it was marked `success`. GitHub sends deployment webhooks on status transitions. Incidents are linked manually or automatically (via the SLA breach Worker). DORA tiers: Elite ≤5%, High 6–10%, Medium 11–30%, Low >30%.

## Solution

```typescript
// workers-cfr-tracker/src/index.ts
export interface Env {
  DB: D1Database;
  GITHUB_WEBHOOK_SECRET: string;
  SLACK_WEBHOOK_URL: string;
  CFR_WINDOW_HOURS: string;      // default '168' (7 days)
  INCIDENT_LINK_WINDOW_HOURS: string; // default '2'
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface DeploymentRow {
  id: string;
  sha: string;
  environment: string;
  deployed_at: number; // unix ms
  status: string;      // 'success' | 'failure' | 'pending'
  linked_incident_id: string | null;
}

interface CfrResult {
  window_hours: number;
  total: number;
  failed: number;
  cfr: number;
  tier: 'elite' | 'high' | 'medium' | 'low';
}

// ---------------------------------------------------------------------------
// DORA tier classification
// ---------------------------------------------------------------------------
function classifyTier(cfr: number): CfrResult['tier'] {
  if (cfr <= 0.05) return 'elite';
  if (cfr <= 0.10) return 'high';
  if (cfr <= 0.30) return 'medium';
  return 'low';
}

// ---------------------------------------------------------------------------
// Webhook signature
// ---------------------------------------------------------------------------
async function verifyGithubSignature(req: Request, secret: string): Promise<boolean> {
  const sig = req.headers.get('X-Hub-Signature-256');
  if (!sig) return false;
  const buf = await req.clone().arrayBuffer();
  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  );
  const mac = await crypto.subtle.sign('HMAC', key, buf);
  const hex = 'sha256=' + [...new Uint8Array(mac)]
    .map(b => b.toString(16).padStart(2, '0')).join('');
  return hex === sig;
}

// ---------------------------------------------------------------------------
// GitHub deployment webhook ingestion
// ---------------------------------------------------------------------------
async function ingestDeploymentStatus(env: Env, payload: any) {
  const ds = payload.deployment_status;
  const dep = payload.deployment;
  if (!ds || !dep) return;

  const id = String(dep.id);
  const sha: string = dep.sha;
  const environment: string = dep.environment ?? 'production';
  const status: string = ds.state; // 'success' | 'failure' | 'error' | 'pending' | 'in_progress'
  const deployedAt = new Date(ds.updated_at).getTime();

  // Upsert deployment record
  await env.DB.prepare(
    `INSERT INTO deployments (id, sha, environment, deployed_at, status, linked_incident_id)
     VALUES (?, ?, ?, ?, ?, NULL)
     ON CONFLICT(id) DO UPDATE SET status = excluded.status, deployed_at = excluded.deployed_at`,
  )
    .bind(id, sha, environment, deployedAt, status)
    .run();

  // Auto-link: scan incidents opened within link window after this deployment
  if (status === 'success') {
    const windowMs = Number(env.INCIDENT_LINK_WINDOW_HOURS || '2') * 3_600_000;
    const windowEnd = deployedAt + windowMs;
    const incident = await env.DB.prepare(
      `SELECT id FROM incidents
       WHERE opened_at BETWEEN ? AND ?
         AND environment = ?
         AND linked_deployment_id IS NULL
       ORDER BY opened_at ASC
       LIMIT 1`,
    )
      .bind(deployedAt, windowEnd, environment)
      .first<{ id: string }>();

    if (incident) {
      await env.DB.prepare(
        `UPDATE deployments SET linked_incident_id = ? WHERE id = ?`,
      ).bind(incident.id, id).run();

      await env.DB.prepare(
        `UPDATE incidents SET linked_deployment_id = ? WHERE id = ?`,
      ).bind(id, incident.id).run();
    }
  }
}

// ---------------------------------------------------------------------------
// CFR computation
// ---------------------------------------------------------------------------
async function computeCfr(env: Env, windowHours?: number): Promise<CfrResult> {
  const hours = windowHours ?? Number(env.CFR_WINDOW_HOURS || '168');
  const since = Date.now() - hours * 3_600_000;

  const row = await env.DB.prepare(
    `SELECT
       COUNT(*) AS total,
       SUM(CASE WHEN linked_incident_id IS NOT NULL THEN 1 ELSE 0 END) AS failed
     FROM deployments
     WHERE status = 'success'
       AND deployed_at >= ?
       AND environment = 'production'`,
  )
    .bind(since)
    .first<{ total: number; failed: number }>();

  const total = row?.total ?? 0;
  const failed = row?.failed ?? 0;
  const cfr = total === 0 ? 0 : failed / total;

  return { window_hours: hours, total, failed, cfr, tier: classifyTier(cfr) };
}

// ---------------------------------------------------------------------------
// Trend endpoint: CFR per day for the past N days
// ---------------------------------------------------------------------------
async function computeTrend(env: Env, days: number = 30): Promise<Array<{
  date: string;
  cfr: number;
  tier: string;
  total: number;
  failed: number;
}>> {
  const rows = await env.DB.prepare(
    `SELECT
       strftime('%Y-%m-%d', datetime(deployed_at / 1000, 'unixepoch')) AS date,
       COUNT(*) AS total,
       SUM(CASE WHEN linked_incident_id IS NOT NULL THEN 1 ELSE 0 END) AS failed
     FROM deployments
     WHERE status = 'success'
       AND environment = 'production'
       AND deployed_at >= ?
     GROUP BY date
     ORDER BY date ASC`,
  )
    .bind(Date.now() - days * 86_400_000)
    .all<{ date: string; total: number; failed: number }>();

  return rows.results.map(r => {
    const cfr = r.total === 0 ? 0 : r.failed / r.total;
    return { date: r.date, cfr, tier: classifyTier(cfr), total: r.total, failed: r.failed };
  });
}

// ---------------------------------------------------------------------------
// Link incident manually
// ---------------------------------------------------------------------------
async function linkIncident(
  env: Env,
  deploymentId: string,
  incidentId: string,
): Promise<Response> {
  const dep = await env.DB.prepare(`SELECT id FROM deployments WHERE id = ?`)
    .bind(deploymentId).first();
  if (!dep) return Response.json({ error: 'Deployment not found' }, { status: 404 });

  await env.DB.prepare(`UPDATE deployments SET linked_incident_id = ? WHERE id = ?`)
    .bind(incidentId, deploymentId).run();

  return Response.json({ ok: true });
}

// ---------------------------------------------------------------------------
// Weekly Slack report (cron)
// ---------------------------------------------------------------------------
async function sendWeeklyReport(env: Env) {
  const current = await computeCfr(env, 168);
  const previous = await computeCfr(env, 336); // previous 7d inside 14d window — approximate
  const trend = await computeTrend(env, 30);

  const tierEmoji: Record<string, string> = {
    elite: ':white_check_mark:',
    high: ':large_green_circle:',
    medium: ':large_yellow_circle:',
    low: ':red_circle:',
  };

  const trendSummary = trend
    .slice(-7)
    .map(d => `${d.date}: ${(d.cfr * 100).toFixed(1)}% (${d.tier})`)
    .join('\n');

  const body = {
    text:
      `${tierEmoji[current.tier]} *Weekly CFR Report*\n` +
      `*Current (7d):* ${(current.cfr * 100).toFixed(1)}% — *${current.tier.toUpperCase()}* ` +
      `(${current.failed}/${current.total} deploys)\n` +
      `*Previous 7d approx:* ${(previous.cfr * 100).toFixed(1)}%\n\n` +
      `*Daily trend (last 7 days):*\n\`\`\`${trendSummary}\`\`\``,
  };

  await fetch(env.SLACK_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (req.method === 'POST' && url.pathname === '/webhook/deployment') {
      const valid = await verifyGithubSignature(req, env.GITHUB_WEBHOOK_SECRET);
      if (!valid) return new Response('Forbidden', { status: 403 });
      const payload = await req.json();
      if (req.headers.get('X-GitHub-Event') === 'deployment_status') {
        await ingestDeploymentStatus(env, payload);
      }
      return new Response('OK');
    }

    if (req.method === 'GET' && url.pathname === '/cfr') {
      const hours = Number(url.searchParams.get('hours') || '168');
      const result = await computeCfr(env, hours);
      return Response.json(result);
    }

    if (req.method === 'GET' && url.pathname === '/cfr/trend') {
      const days = Number(url.searchParams.get('days') || '30');
      const trend = await computeTrend(env, days);
      return Response.json(trend);
    }

    if (req.method === 'POST' && url.pathname === '/link-incident') {
      const { deployment_id, incident_id } = await req.json<{
        deployment_id: string;
        incident_id: string;
      }>();
      return linkIncident(env, deployment_id, incident_id);
    }

    return new Response('Not found', { status: 404 });
  },

  async scheduled(_event: ScheduledEvent, env: Env) {
    // Weekly report every Monday at 09:00 UTC — cron: '0 9 * * 1'
    await sendWeeklyReport(env);
  },
};
```

**D1 schema:**

```sql
CREATE TABLE deployments (
  id                  TEXT PRIMARY KEY,
  sha                 TEXT NOT NULL,
  environment         TEXT NOT NULL DEFAULT 'production',
  deployed_at         INTEGER NOT NULL,  -- unix ms
  status              TEXT NOT NULL,
  linked_incident_id  TEXT
);

CREATE TABLE incidents (
  id                    TEXT PRIMARY KEY,
  title                 TEXT NOT NULL,
  severity              TEXT NOT NULL,
  environment           TEXT NOT NULL DEFAULT 'production',
  opened_at             INTEGER NOT NULL,
  resolved_at           INTEGER,
  linked_deployment_id  TEXT
);

CREATE INDEX idx_deployments_deployed_at ON deployments(deployed_at);
CREATE INDEX idx_incidents_opened_at ON incidents(opened_at);
```

**wrangler.toml:**

```toml
[triggers]
crons = ["0 9 * * 1"]

[vars]
CFR_WINDOW_HOURS = "168"
INCIDENT_LINK_WINDOW_HOURS = "2"
```

## Implementation Details

- CFR is computed from `deployments` where `status = 'success'` and `linked_incident_id IS NOT NULL`. Deployments that failed CI/CD (`status = 'failure'`) are excluded — DORA CFR only counts deployments that reached production.
- Auto-linking scans a time window after the deployment's `deployed_at`. The window is configurable via `INCIDENT_LINK_WINDOW_HOURS`.
- The trend query uses SQLite's `strftime` to bucket by calendar day in UTC.
- The weekly cron computes two overlapping windows to approximate period-over-period comparison; for exact comparison, store weekly snapshots in a separate table.

## Anti-patterns

- **Including non-production environments in CFR.** Staging incidents inflate the rate and misrepresent the DORA metric. Always filter by `environment = 'production'`.
- **Counting deployment failures (CI/CD pipeline failures) as CFR events.** DORA CFR is specifically about deployments that caused production incidents, not builds that failed before reaching production.
- **Linking incidents to deployments by time proximity alone without human review.** Auto-linking is a convenience; always provide a `/link-incident` manual override.
- **Computing CFR over an unbounded window.** Very old data distorts trending; use explicit rolling windows.

## Gotchas

- GitHub sends `deployment_status` events for every intermediate state (`pending`, `in_progress`). Only process `success` for CFR purposes.
- D1's `strftime` function operates on Unix epoch seconds, not milliseconds. Divide `deployed_at` by 1000 in the SQL as shown.
- If the `INCIDENT_LINK_WINDOW_HOURS` window is too long, unrelated incidents may be linked to deployments. Start with 2 hours and tune.
- The Cron expression `0 9 * * 1` fires on Mondays at 09:00 UTC. Adjust for your team's timezone.

## Verification

1. POST a `deployment_status` webhook for a successful deployment. Assert the row is inserted in `deployments` with `status = 'success'`.
2. Insert an incident with `opened_at` within the link window. Re-trigger the link check. Assert `linked_incident_id` is populated on the deployment row.
3. `GET /cfr?hours=168`. Assert `failed/total` matches the number of linked deployments in the window.
4. `GET /cfr/trend?days=7`. Assert one row per calendar day with correct `cfr` values.
5. Run `wrangler dev --test-scheduled` and assert the Slack webhook receives a formatted weekly report.

## Related

- `workers-sla-breach-auto-escalation.md` — incidents that drive CFR
- `workers-postmortem-generator.md` — postmortem action items linked to high-CFR periods
- `workers-github-issue-triage-bot.md` — deployment-related issues auto-triaged

## Sources

- https://dora.dev/guides/dora-metrics-four-keys/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/d1/
- https://docs.github.com/en/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#deployment_status
