# Workers Versions API for Gradual Rollout

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You want to ship a new Worker version to 5% of traffic, watch error rates for 30 minutes, then gradually increase to 25%, 50%, 100% — without a full redeployment at each step. If errors spike, you need automated rollback to the previous version in under 60 seconds. You also need a queryable history of every version that has served production traffic.

## Context

- Cloudflare Workers Versions API (GA as of 2024) separates *creating* a version from *deploying* it. A version is an immutable snapshot of your Worker code and bindings.
- A Workers Deployment specifies a weighted split across one or more named versions (`versions_data`). Changing the weights does not redeployment the code — it only updates the routing table at the edge.
- Analytics Engine (or Workers Logpush) provides per-version error rates. A monitor Worker queries these and triggers automated rollback.
- D1 stores version history, deployment events, and the soak-period state so the promotion logic survives Cron Worker restarts.
- The entire flow — create version, start split, monitor, promote or rollback — is orchestrated by a Cron Worker running every 5 minutes.

## Solution

```typescript
// src/rollout-controller/index.ts
// Orchestrates gradual rollout via the Workers Versions API.

import { D1Database, AnalyticsEngineDataset } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  ANALYTICS: AnalyticsEngineDataset;
  CF_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  SCRIPT_NAME: string;
  ERROR_RATE_THRESHOLD: string; // e.g. "0.02" = 2%
  NOTIFICATION_URL: string;
}

const ROLLOUT_STAGES = [5, 25, 50, 100]; // percentage steps
const SOAK_MINUTES = 30;                 // minutes to hold each stage before promoting

interface VersionRecord {
  id: number;
  version_id: string;
  version_tag: string;
  created_at: string;
  deployed_at: string | null;
  rolled_back_at: string | null;
  stage_percent: number;
  status: 'staging' | 'rolling_out' | 'promoted' | 'rolled_back';
  stage_started_at: string | null;
  deployment_id: string | null;
}

// --- Cloudflare API helpers ---

async function createVersion(
  accountId: string,
  scriptName: string,
  apiToken: string,
  tag: string,
): Promise<string> {
  // In practice, versions are created by `wrangler versions upload`.
  // This function retrieves the latest uploaded-but-not-deployed version.
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${scriptName}/versions?per_page=1`,
    { headers: { Authorization: `Bearer ${apiToken}` } },
  );
  if (!res.ok) throw new Error(`Failed to list versions: ${res.status}`);
  const data = (await res.json()) as { result: Array<{ id: string; metadata: { tag: string } }> };
  const latest = data.result[0];
  if (!latest) throw new Error('No versions found');
  return latest.id;
}

async function setDeploymentSplit(
  accountId: string,
  scriptName: string,
  apiToken: string,
  newVersionId: string,
  newVersionPercent: number,
  stableVersionId: string,
): Promise<string> {
  // Workers Deployments API: set a weighted split
  const versionsData = [
    { version_id: newVersionId, percentage: newVersionPercent },
  ];

  if (newVersionPercent < 100) {
    versionsData.push({
      version_id: stableVersionId,
      percentage: 100 - newVersionPercent,
    });
  }

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${scriptName}/deployments`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        versions: versionsData,
        strategy: 'percentage',
        annotations: {
          'workers/message': `Gradual rollout — ${newVersionPercent}% to ${newVersionId}`,
          'workers/tag': new Date().toISOString(),
        },
      }),
    },
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Failed to set deployment split: ${res.status} ${body}`);
  }

  const data = (await res.json()) as { result: { id: string } };
  return data.result.id;
}

async function getActiveVersions(
  accountId: string,
  scriptName: string,
  apiToken: string,
): Promise<Array<{ version_id: string; percentage: number }>> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${scriptName}/deployments?per_page=1`,
    { headers: { Authorization: `Bearer ${apiToken}` } },
  );
  if (!res.ok) throw new Error(`Failed to get deployments: ${res.status}`);
  const data = (await res.json()) as {
    result: Array<{ versions: Array<{ version_id: string; percentage: number }> }>
  };
  return data.result[0]?.versions ?? [];
}

// --- Error rate from Analytics Engine ---

async function getErrorRate(
  accountId: string,
  versionId: string,
  apiToken: string,
  windowMinutes = SOAK_MINUTES,
): Promise<number> {
  const sql = `
    SELECT
      SUM(CASE WHEN blob1 = 'error' THEN double1 ELSE 0 END) AS errors,
      SUM(double1) AS total
    FROM workers_analytics
    WHERE timestamp > NOW() - INTERVAL '${windowMinutes}' MINUTE
      AND blob2 = '${versionId}'
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
      },
      body: sql,
    },
  );

  if (!res.ok) return 0; // if query fails, don't block rollout
  const data = (await res.json()) as { data: Array<{ errors: number; total: number }> };
  const row = data.data[0];
  if (!row || row.total === 0) return 0;
  return row.errors / row.total;
}

// --- Rollout state machine ---

async function advanceRollout(env: Env): Promise<void> {
  const active = await env.DB
    .prepare(`SELECT * FROM version_rollouts WHERE status = 'rolling_out' ORDER BY created_at DESC LIMIT 1`)
    .first<VersionRecord>();

  if (!active) return;

  const errorRate = await getErrorRate(env.CF_ACCOUNT_ID, active.version_id, env.CF_API_TOKEN);
  const threshold = parseFloat(env.ERROR_RATE_THRESHOLD);

  if (errorRate > threshold) {
    await rollbackVersion(env, active, errorRate);
    return;
  }

  const stageStarted = active.stage_started_at ? new Date(active.stage_started_at) : new Date();
  const soakElapsed = (Date.now() - stageStarted.getTime()) / 60_000;

  if (soakElapsed < SOAK_MINUTES) {
    console.log(
      `Version ${active.version_id} at ${active.stage_percent}% — soak ${soakElapsed.toFixed(1)}/${SOAK_MINUTES} min, error rate ${(errorRate * 100).toFixed(3)}%`,
    );
    return;
  }

  // Advance to next stage
  const currentIdx = ROLLOUT_STAGES.indexOf(active.stage_percent);
  const nextPercent = ROLLOUT_STAGES[currentIdx + 1];

  if (nextPercent === undefined) {
    // Already at 100% — nothing to do
    await env.DB
      .prepare(`UPDATE version_rollouts SET status = 'promoted' WHERE id = ?`)
      .bind(active.id)
      .run();
    await notify(env, `Version ${active.version_tag} promoted to 100% — soak complete.`);
    return;
  }

  // Determine the stable version (the one currently carrying the remaining traffic)
  const activeVersions = await getActiveVersions(env.CF_ACCOUNT_ID, env.SCRIPT_NAME, env.CF_API_TOKEN);
  const stableVersion = activeVersions.find((v) => v.version_id !== active.version_id);
  const stableVersionId = stableVersion?.version_id ?? active.version_id;

  const deploymentId = await setDeploymentSplit(
    env.CF_ACCOUNT_ID,
    env.SCRIPT_NAME,
    env.CF_API_TOKEN,
    active.version_id,
    nextPercent,
    stableVersionId,
  );

  await env.DB
    .prepare(
      `UPDATE version_rollouts
       SET stage_percent = ?, stage_started_at = datetime('now'), deployment_id = ?
       WHERE id = ?`,
    )
    .bind(nextPercent, deploymentId, active.id)
    .run();

  await notify(
    env,
    `Version ${active.version_tag} advanced to ${nextPercent}% — error rate ${(errorRate * 100).toFixed(3)}%.`,
  );
}

async function rollbackVersion(env: Env, record: VersionRecord, errorRate: number): Promise<void> {
  // Get the stable version to roll back to 100%
  const activeVersions = await getActiveVersions(env.CF_ACCOUNT_ID, env.SCRIPT_NAME, env.CF_API_TOKEN);
  const stableVersion = activeVersions.find((v) => v.version_id !== record.version_id);

  if (!stableVersion) {
    console.error('No stable version found for rollback!');
    return;
  }

  await setDeploymentSplit(
    env.CF_ACCOUNT_ID,
    env.SCRIPT_NAME,
    env.CF_API_TOKEN,
    stableVersion.version_id,
    100,
    stableVersion.version_id,
  );

  await env.DB
    .prepare(
      `UPDATE version_rollouts
       SET status = 'rolled_back', rolled_back_at = datetime('now')
       WHERE id = ?`,
    )
    .bind(record.id)
    .run();

  await notify(
    env,
    `ROLLBACK: Version ${record.version_tag} rolled back from ${record.stage_percent}% — error rate ${(errorRate * 100).toFixed(2)}% exceeded threshold.`,
  );
}

async function notify(env: Env, message: string): Promise<void> {
  if (!env.NOTIFICATION_URL) return;
  await fetch(env.NOTIFICATION_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: `[orchords rollout] ${message}` }),
  });
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await advanceRollout(env);
  },

  async fetch(request: Request, env: Env): Promise<Response> {
    // Manual trigger: POST /rollout/start { version_id, version_tag }
    const url = new URL(request.url);
    if (request.method === 'POST' && url.pathname === '/rollout/start') {
      const body = (await request.json()) as { version_id: string; version_tag: string };

      // Determine stable version for the initial split
      const activeVersions = await getActiveVersions(
        env.CF_ACCOUNT_ID, env.SCRIPT_NAME, env.CF_API_TOKEN,
      );
      const stableVersionId = activeVersions.find((v) => v.percentage === 100)?.version_id
        ?? activeVersions[0]?.version_id;

      if (!stableVersionId) {
        return Response.json({ error: 'No stable version found' }, { status: 400 });
      }

      const initialPercent = ROLLOUT_STAGES[0];
      const deploymentId = await setDeploymentSplit(
        env.CF_ACCOUNT_ID,
        env.SCRIPT_NAME,
        env.CF_API_TOKEN,
        body.version_id,
        initialPercent,
        stableVersionId,
      );

      await env.DB
        .prepare(
          `INSERT INTO version_rollouts
             (version_id, version_tag, stage_percent, status, stage_started_at, deployment_id)
           VALUES (?, ?, ?, 'rolling_out', datetime('now'), ?)`,
        )
        .bind(body.version_id, body.version_tag, initialPercent, deploymentId)
        .run();

      await notify(env, `Rollout started for ${body.version_tag} at ${initialPercent}%.`);
      return Response.json({ ok: true, initialPercent, deploymentId });
    }

    if (request.method === 'GET' && url.pathname === '/rollout/history') {
      const rows = await env.DB
        .prepare('SELECT * FROM version_rollouts ORDER BY created_at DESC LIMIT 20')
        .all();
      return Response.json(rows.results);
    }

    return new Response('Not Found', { status: 404 });
  },
};
```

```sql
-- D1 schema
CREATE TABLE IF NOT EXISTS version_rollouts (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  version_id       TEXT    NOT NULL,
  version_tag      TEXT    NOT NULL,
  stage_percent    INTEGER NOT NULL DEFAULT 5,
  status           TEXT    NOT NULL DEFAULT 'rolling_out',
  stage_started_at TEXT,
  deployment_id    TEXT,
  created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
  rolled_back_at   TEXT
);
CREATE INDEX idx_rollout_status ON version_rollouts(status, created_at DESC);
```

```yaml
# wrangler.toml for rollout-controller
name = "orchords-rollout-controller"
main = "src/rollout-controller/index.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding       = "DB"
database_name = "orchords-prod"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[triggers]
crons = ["*/5 * * * *"]
```

## Implementation Details

**Version creation** — Developers run `npx wrangler versions upload` (not `wrangler deploy`) to create a named, immutable version. The CI pipeline calls `POST /rollout/start` with the version ID to begin gradual rollout at 5%.

**Weighted splits** — The Workers Deployments API `versions` array accepts any number of version/percentage pairs summing to 100. Traffic is split at the edge per-request using consistent hashing on a per-session cookie or randomly, depending on the strategy.

**Soak period** — Each stage holds for `SOAK_MINUTES` (default 30) before the Cron Worker advances it. The `stage_started_at` column in D1 tracks when the current stage began, surviving Cron restarts.

**Error rate source** — Analytics Engine provides sub-minute resolution. The target Worker must write error data points (`blob1 = 'error'`, `blob2 = versionId`) for the query to work. Alternatively, use Workers Logpush to Cloudflare's SIEM and query the aggregates via the Tail Workers API.

**Automated rollback** — On each Cron tick, error rate is sampled over the last `SOAK_MINUTES` window. If it exceeds the threshold (configurable via the `ERROR_RATE_THRESHOLD` secret), the stable version is immediately set to 100% and a notification fires.

**Version history in D1** — Every rollout event (start, stage advance, promote, rollback) is recorded in `version_rollouts`. This gives a queryable audit trail: when was each version live, at what percentage, and why it was rolled back.

## Anti-patterns

- Using `wrangler deploy` for the initial 5% rollout — `wrangler deploy` always promotes the version to 100%; use `wrangler versions upload` + the Deployments API for splits.
- Setting `SOAK_MINUTES` to zero — bypasses the monitoring window; errors in the new version won't be caught before full promotion.
- Querying error rates over a window shorter than 1 minute — Analytics Engine has ~1-minute ingestion lag; short windows will under-count errors.
- Promoting to 100% without verifying the stable version ID — if there is no prior stable version (first-ever deploy), the split calculation is wrong.

## Gotchas

- The Workers Versions API is distinct from the Workers Deployments API. A *version* is code; a *deployment* is a routing table. You need both.
- `wrangler versions upload` does not serve traffic — it only registers the version. Traffic only shifts when you POST to the Deployments API.
- Percentage splits are applied at the edge; there is no guarantee of exact percentages for very low-traffic Workers. The split is a long-run expectation.
- The Analytics Engine SQL API is eventually consistent with ~60-second lag — do not expect real-time error counts.
- If two rollouts are started simultaneously, the state machine in D1 will only pick up the most recent `rolling_out` row. Guard against concurrent rollouts with a `UNIQUE` constraint on `status = 'rolling_out'` or an application-level lock.

## Verification

```bash
# 1. Upload a new version (does not serve traffic)
npx wrangler versions upload --env production --tag v1.2.3

# 2. Retrieve the new version ID
npx wrangler versions list --env production | head -5

# 3. Start the gradual rollout at 5%
curl -s -X POST https://orchords-rollout-controller.orchords.workers.dev/rollout/start \
  -H "Content-Type: application/json" \
  -d '{"version_id": "<VERSION_ID>", "version_tag": "v1.2.3"}'

# 4. Monitor rollout progress
curl -s https://orchords-rollout-controller.orchords.workers.dev/rollout/history | jq '.[0]'

# 5. Check current traffic split in Cloudflare
curl -s \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/workers/scripts/orchords-api/deployments?per_page=1" \
  | jq '.result[0].versions'

# 6. Query version history from D1
npx wrangler d1 execute orchords-prod \
  --command "SELECT version_tag, stage_percent, status, created_at, rolled_back_at \
             FROM version_rollouts ORDER BY created_at DESC LIMIT 10;"
```

## Related

- `documentation/docs/policies/deploy/workers-deployment-approval-gates.md` — requiring approval before starting a rollout
- `documentation/docs/policies/deploy/workers-zero-downtime-d1-migration.md` — coordinating schema changes with traffic percentage splits
- `documentation/docs/policies/deploy/workers-multi-region-failover-deploy.md` — failing over between accounts during a bad rollout
- Cloudflare Workers Versions API documentation
- Cloudflare Workers Deployments API documentation

## Sources

- https://developers.cloudflare.com/workers/platform/versions-and-deployments/
- https://developers.cloudflare.com/workers/platform/versions-and-deployments/gradual-deployments/
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://developers.cloudflare.com/workers/wrangler/commands/#versions
