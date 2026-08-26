# MTTD Tracking in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Engineering teams need to measure Mean Time to Detect (MTTD) — the gap between when a failure begins and when an alert fires — across multiple monitoring systems (PagerDuty, Grafana, custom webhook sources). Without a unified ingest pipeline, MTTD data lives in silos, DORA reporting is manual, and teams cannot compare detection latency across services or regions.

## Context

MTTD is a leading reliability indicator. A high MTTD means failures are affecting users silently before engineers know. Cloudflare Workers can act as a neutral aggregation point: every monitoring system posts alert events to a single `/ingest/alert` endpoint; the Worker correlates each alert with its incident record in D1 and writes the detection delta in milliseconds. Scheduled Workers generate DORA-style trending data nightly.

Prerequisites:
- D1 database bound as `DB`
- KV namespace bound as `ALERT_CACHE` (deduplication window)
- PagerDuty, Grafana, and custom sources configured to POST to the Worker

## Solution

```typescript
// worker-mttd.ts
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
  ALERT_CACHE: KVNamespace;
  INGEST_SECRET: string;
}

interface AlertEvent {
  source: 'pagerduty' | 'grafana' | 'custom';
  alertId: string;
  service: string;
  region: string;
  severity: 'critical' | 'warning' | 'info';
  firedAt: string;        // ISO-8601, when the monitoring system fired
  incidentStartAt: string; // ISO-8601, estimated failure start (from anomaly detection or deploy time)
  incidentId?: string;   // if already linked
}

interface MttdRecord {
  id: string;
  alertId: string;
  incidentId: string;
  source: string;
  service: string;
  region: string;
  severity: string;
  alertFiredAt: number;     // epoch ms
  incidentStartAt: number;  // epoch ms
  mttdMs: number;
  createdAt: number;
}

const app = new Hono<{ Bindings: Env }>();

// --- schema bootstrap (run once via /init) ---
const SCHEMA = `
CREATE TABLE IF NOT EXISTS mttd_records (
  id TEXT PRIMARY KEY,
  alert_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  source TEXT NOT NULL,
  service TEXT NOT NULL,
  region TEXT NOT NULL,
  severity TEXT NOT NULL,
  alert_fired_at INTEGER NOT NULL,
  incident_start_at INTEGER NOT NULL,
  mttd_ms INTEGER NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mttd_service ON mttd_records(service, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mttd_incident ON mttd_records(incident_id);
`;

app.post('/init', async (c) => {
  for (const stmt of SCHEMA.split(';').map(s => s.trim()).filter(Boolean)) {
    await c.env.DB.prepare(stmt).run();
  }
  return c.json({ ok: true });
});

// --- alert ingest ---
app.post('/ingest/alert', async (c) => {
  const secret = <redacted-secret>'x-ingest-secret');
  if (secret !== c.env.INGEST_SECRET) return c.json({ error: 'unauthorized' }, 401);

  const body = await c.req.json<AlertEvent>();
  const dedupeKey = `alert:${body.source}:${body.alertId}`;

  // Dedup: ignore if we already processed this alert within 10 minutes
  const existing = await c.env.ALERT_CACHE.get(dedupeKey);
  if (existing) return c.json({ ok: true, duplicate: true });
  await c.env.ALERT_CACHE.put(dedupeKey, '1', { expirationTtl: 600 });

  const alertFiredAt = new Date(body.firedAt).getTime();
  const incidentStartAt = new Date(body.incidentStartAt).getTime();

  if (isNaN(alertFiredAt) || isNaN(incidentStartAt)) {
    return c.json({ error: 'invalid timestamps' }, 400);
  }

  const mttdMs = Math.max(0, alertFiredAt - incidentStartAt);
  const incidentId = body.incidentId ?? `auto:${body.service}:${incidentStartAt}`;
  const id = crypto.randomUUID();
  const now = Date.now();

  await c.env.DB.prepare(`
    INSERT INTO mttd_records
      (id, alert_id, incident_id, source, service, region, severity,
       alert_fired_at, incident_start_at, mttd_ms, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    id, body.alertId, incidentId, body.source,
    body.service, body.region, body.severity,
    alertFiredAt, incidentStartAt, mttdMs, now
  ).run();

  return c.json({ ok: true, id, mttdMs });
});

// --- DORA-style MTTD trend (last N days, per service) ---
app.get('/metrics/mttd/trend', async (c) => {
  const days = parseInt(c.req.query('days') ?? '30', 10);
  const service = c.req.query('service'); // optional filter
  const since = Date.now() - days * 86_400_000;

  const base = `
    SELECT
      service,
      date(created_at / 1000, 'unixepoch') AS day,
      COUNT(*) AS alert_count,
      AVG(mttd_ms) AS avg_mttd_ms,
      MIN(mttd_ms) AS min_mttd_ms,
      MAX(mttd_ms) AS max_mttd_ms
    FROM mttd_records
    WHERE created_at >= ?
    ${service ? 'AND service = ?' : ''}
    GROUP BY service, day
    ORDER BY day DESC, avg_mttd_ms DESC
  `;

  const { results } = service
    ? await c.env.DB.prepare(base).bind(since, service).all()
    : await c.env.DB.prepare(base).bind(since).all();

  return c.json({ days, results });
});

// --- Team comparison: p50/p90 MTTD per service ---
app.get('/metrics/mttd/teams', async (c) => {
  const since = Date.now() - 90 * 86_400_000; // last 90 days

  // D1 does not have native percentile functions; we pull per-service sorted arrays
  const { results } = await c.env.DB.prepare(`
    SELECT service, mttd_ms
    FROM mttd_records
    WHERE created_at >= ?
    ORDER BY service, mttd_ms
  `).bind(since).all<{ service: string; mttd_ms: number }>();

  // Group and calculate percentiles in JS
  const groups = new Map<string, number[]>();
  for (const row of results) {
    const arr = groups.get(row.service) ?? [];
    arr.push(row.mttd_ms);
    groups.set(row.service, arr);
  }

  const percentile = (arr: number[], p: number) =>
    arr[Math.floor(arr.length * p / 100)] ?? 0;

  const summary = [...groups.entries()].map(([service, arr]) => ({
    service,
    count: arr.length,
    p50_ms: percentile(arr, 50),
    p90_ms: percentile(arr, 90),
    avg_ms: Math.round(arr.reduce((a, b) => a + b, 0) / arr.length),
  }));

  summary.sort((a, b) => b.p90_ms - a.p90_ms);
  return c.json({ since: new Date(since).toISOString(), teams: summary });
});

export default {
  fetch: app.fetch,

  // Nightly scheduled export to KV for dashboard consumption
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const since = Date.now() - 24 * 86_400_000;
    const { results } = await env.DB.prepare(`
      SELECT service, AVG(mttd_ms) AS avg_mttd_ms, COUNT(*) AS count
      FROM mttd_records
      WHERE created_at >= ?
      GROUP BY service
    `).bind(since).all();

    await env.ALERT_CACHE.put(
      'mttd:daily_snapshot',
      JSON.stringify({ generatedAt: new Date().toISOString(), results }),
      { expirationTtl: 90 * 86_400 }
    );
  }
};
```

## Implementation Details

- **Dedup window**: KV with 10-minute TTL prevents double-counting when PagerDuty retries its webhook. Extend to 30 minutes for noisy sources.
- **Incident start estimation**: `incidentStartAt` should be the anomaly detection timestamp, not the alert fire time. Grafana can supply this via its `startsAt` field; PagerDuty's `triggered_at` is the page time, not the failure start — use the linked metric annotation or a preceding deploy timestamp instead.
- **DORA mapping**: MTTD maps loosely to DORA's "time to restore" leading indicator. Track it alongside MTTR to distinguish detection lag from remediation lag.
- **Percentile calculation**: D1 lacks `PERCENTILE_CONT`; pulling sorted rows into the Worker runtime is efficient for fewer than ~10 000 rows per query window. For larger datasets, maintain running buckets in a nightly aggregation table.
- **Timezone**: All timestamps stored as epoch milliseconds in UTC. `date(..., 'unixepoch')` in SQLite returns UTC dates — consistent with the JS `Date` class.

## Anti-patterns

- **Using alert fire time as incident start**: This produces MTTD = 0 for every alert, making the metric meaningless. Always source `incidentStartAt` from an independent signal (anomaly baseline, deployment timestamp, synthetic monitor first failure).
- **Skipping deduplication**: Monitoring systems retry webhooks on network errors. Without dedup, a single alert inflates counts and distorts averages.
- **Polling D1 for real-time dashboards**: Grafana or similar tools should read from the KV daily snapshot; hitting D1 per dashboard refresh at high frequency exhausts request budgets.
- **Mixing severity levels in aggregates**: P90 MTTD for critical alerts is far more actionable than a mixed-severity average. Always segment by severity in DORA reporting.

## Gotchas

- PagerDuty sends `trigger`, `acknowledge`, and `resolve` event types on the same webhook endpoint. Filter to `trigger` only; otherwise `acknowledge` events create phantom MTTD records.
- Grafana unified alerting fires `alerting` and `resolved` states. Map `alerting` → ingest; ignore `resolved` here (handle it in the dedup/incident correlation flow).
- D1's SQLite `AVG()` returns `NULL` for empty groups; coerce with `COALESCE(AVG(mttd_ms), 0)` in production queries.
- The `incidentStartAt` field accepts ISO-8601 strings. Validate strictly — some sources send Unix seconds (not milliseconds); multiply by 1000 before storing.

## Verification

```bash
# 1. Bootstrap schema
curl -X POST https://mttd-worker.your-domain.workers.dev/init

# 2. Ingest a test alert (MTTD should be 300 000 ms = 5 minutes)
curl -X POST https://mttd-worker.your-domain.workers.dev/ingest/alert \
  -H 'Content-Type: application/json' \
  -H 'x-ingest-secret: YOUR_SECRET' \
  -d '{
    "source": "grafana",
    "alertId": "test-001",
    "service": "checkout",
    "region": "us-east-1",
    "severity": "critical",
    "firedAt": "2026-08-24T10:05:00Z",
    "incidentStartAt": "2026-08-24T10:00:00Z",
    "incidentId": "INC-9999"
  }'
# Expected: {"ok":true,"mttdMs":300000}

# 3. Check trend
curl 'https://mttd-worker.your-domain.workers.dev/metrics/mttd/trend?days=7&service=checkout'

# 4. Confirm nightly snapshot was written (after scheduled run)
wrangler kv key get --namespace-id=<NS_ID> 'mttd:daily_snapshot'
```

## Related

- `documentation/docs/policies/issues/workers-incident-timeline-reconstruction.md` — correlates alert timestamps with deploy events
- `documentation/docs/policies/issues/workers-error-budget-tracker.md` — consumes MTTD data for SLO burn-rate calculations
- `documentation/docs/policies/issues/workers-alert-correlation-dedup.md` — upstream dedup pipeline that feeds this ingest endpoint
- `documentation/docs/policies/issues/workers-sla-breach-auto-escalation.md` — downstream escalation triggered when MTTD exceeds SLA threshold

## Sources

- [DORA Metrics — Google Cloud DevOps Research](https://cloud.google.com/devops/state-of-devops)
- [Cloudflare D1 SQL API](https://developers.cloudflare.com/d1/worker-api/)
- [PagerDuty Webhook V3 Reference](https://developer.pagerduty.com/docs/ZG9jOjExMDI5NTc4-v3-overview)
- [Grafana Unified Alerting Webhook](https://grafana.com/docs/grafana/latest/alerting/alerting-rules/manage-contact-points/integrations/webhook-notifier/)
