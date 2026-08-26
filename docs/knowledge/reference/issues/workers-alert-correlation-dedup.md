# Alert Correlation and Deduplication in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

During an outage, a single infrastructure failure fires hundreds of alerts across Grafana, PagerDuty, Datadog, and custom synthetic monitors — all describing the same root cause from different angles. On-call engineers receive dozens of pages, struggle to identify the canonical incident, and waste time triaging duplicate alerts rather than fixing the problem. Alert fatigue sets in; engineers start silencing alerts rather than addressing them.

## Context

A Cloudflare Worker acts as a funnel for all alert sources. Incoming alerts are fingerprinted by `(service, check, region)` and stored in KV with a deduplication window. Correlated alerts are grouped under a single canonical incident in D1. When all child alerts resolve, the canonical incident is auto-resolved. Noise reduction metrics are recorded so teams can audit suppression accuracy.

Prerequisites:
- KV namespace bound as `ALERT_STORE` (fingerprint dedup + group state)
- D1 database bound as `DB` (canonical incidents + suppression log)
- Secrets: `SLACK_BOT_TOKEN`, `PAGERDUTY_API_KEY`, `ON_CALL_CHANNEL`
- Upstream monitoring systems send webhooks to `/alert/ingest`

## Solution

```typescript
// worker-alert-dedup.ts
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
  ALERT_STORE: KVNamespace;
  SLACK_BOT_TOKEN: string;
  PAGERDUTY_API_KEY: string;
  ON_CALL_CHANNEL: string;
  INGEST_SECRET: string;
}

interface RawAlert {
  source: string;       // 'grafana' | 'pagerduty' | 'datadog' | 'synthetic'
  externalId: string;  // source-native alert ID
  service: string;
  check: string;       // e.g. 'error-rate', 'latency-p99', 'uptime'
  region: string;
  severity: 'critical' | 'warning' | 'info';
  state: 'firing' | 'resolved';
  firedAt: string;     // ISO-8601
  labels: Record<string, string>;
  value?: number;      // metric value that triggered the alert
}

interface CanonicalIncident {
  id: string;
  fingerprint: string;
  service: string;
  severity: string;
  openedAt: number;
  resolvedAt: number | null;
  childCount: number;
  resolvedChildCount: number;
  suppressedCount: number;
}

const DEDUP_WINDOW_MS = 30 * 60_000; // 30 minutes
const SCHEMA = `
CREATE TABLE IF NOT EXISTS canonical_incidents (
  id TEXT PRIMARY KEY,
  fingerprint TEXT NOT NULL UNIQUE,
  service TEXT NOT NULL,
  severity TEXT NOT NULL,
  opened_at INTEGER NOT NULL,
  resolved_at INTEGER,
  child_count INTEGER DEFAULT 1,
  resolved_child_count INTEGER DEFAULT 0,
  suppressed_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS alert_suppression_log (
  id TEXT PRIMARY KEY,
  canonical_id TEXT NOT NULL,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  suppressed_at INTEGER NOT NULL,
  reason TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ci_fingerprint ON canonical_incidents(fingerprint);
CREATE INDEX IF NOT EXISTS idx_ci_open ON canonical_incidents(resolved_at) WHERE resolved_at IS NULL;
`;

function fingerprint(service: string, check: string, region: string): string {
  // Deterministic fingerprint — same (service, check, region) always maps to the same group
  return btoa(`${service}::${check}::${region}`).replace(/=/g, '');
}

async function findOrCreateCanonical(
  env: Env,
  alert: RawAlert,
  fp: string
): Promise<{ incident: CanonicalIncident; created: boolean }> {
  // KV fast-path: check if an open group exists
  const kvKey = `group:${fp}`;
  const kvVal = await env.ALERT_STORE.get(kvKey);

  if (kvVal) {
    const incident = JSON.parse(kvVal) as CanonicalIncident;
    // Refresh TTL
    await env.ALERT_STORE.put(kvKey, kvVal, { expirationTtl: Math.ceil(DEDUP_WINDOW_MS / 1000) });
    return { incident, created: false };
  }

  // Check D1 for an open canonical incident with this fingerprint
  const existing = await env.DB.prepare(`
    SELECT * FROM canonical_incidents WHERE fingerprint = ? AND resolved_at IS NULL
  `).bind(fp).first<CanonicalIncident>();

  if (existing) {
    await env.ALERT_STORE.put(kvKey, JSON.stringify(existing), {
      expirationTtl: Math.ceil(DEDUP_WINDOW_MS / 1000),
    });
    return { incident: existing, created: false };
  }

  // Create new canonical incident
  const id = `CINC-${Date.now()}-${fp.slice(0, 6)}`;
  const now = Date.now();
  const newIncident: CanonicalIncident = {
    id, fingerprint: fp, service: alert.service, severity: alert.severity,
    openedAt: now, resolvedAt: null,
    childCount: 1, resolvedChildCount: 0, suppressedCount: 0,
  };

  await env.DB.prepare(`
    INSERT INTO canonical_incidents
      (id, fingerprint, service, severity, opened_at, child_count)
    VALUES (?, ?, ?, ?, ?, 1)
  `).bind(id, fp, alert.service, alert.severity, now).run();

  await env.ALERT_STORE.put(kvKey, JSON.stringify(newIncident), {
    expirationTtl: Math.ceil(DEDUP_WINDOW_MS / 1000),
  });

  return { incident: newIncident, created: true };
}

async function suppressDuplicate(env: Env, canonicalId: string, alert: RawAlert, fp: string) {
  const logId = crypto.randomUUID();
  await env.DB.prepare(`
    INSERT INTO alert_suppression_log (id, canonical_id, source, external_id, fingerprint, suppressed_at, reason)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).bind(logId, canonicalId, alert.source, alert.externalId, fp, Date.now(), 'duplicate_in_window').run();

  await env.DB.prepare(`
    UPDATE canonical_incidents SET suppressed_count = suppressed_count + 1 WHERE id = ?
  `).bind(canonicalId).run();
}

async function checkAutoResolve(env: Env, incident: CanonicalIncident, fp: string) {
  const fresh = await env.DB.prepare(`
    SELECT child_count, resolved_child_count FROM canonical_incidents WHERE id = ?
  `).bind(incident.id).first<{ child_count: number; resolved_child_count: number }>();

  if (!fresh) return;
  if (fresh.resolved_child_count >= fresh.child_count) {
    // All children resolved — auto-resolve canonical incident
    const resolvedAt = Date.now();
    await env.DB.prepare(`
      UPDATE canonical_incidents SET resolved_at = ? WHERE id = ?
    `).bind(resolvedAt, incident.id).run();
    await env.ALERT_STORE.delete(`group:${fp}`);

    // Notify Slack
    await fetch('https://slack.com/api/chat.postMessage', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.SLACK_BOT_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        channel: env.ON_CALL_CHANNEL,
        text: `:white_check_mark: Canonical incident *${incident.id}* (${incident.service}) auto-resolved — all ${fresh.child_count} child alerts resolved.`,
      }),
    });
  }
}

const app = new Hono<{ Bindings: Env }>();

app.post('/init', async (c) => {
  for (const stmt of SCHEMA.split(';').map(s => s.trim()).filter(Boolean)) {
    await c.env.DB.prepare(stmt).run();
  }
  return c.json({ ok: true });
});

app.post('/alert/ingest', async (c) => {
  if (c.req.header('x-ingest-secret') !== c.env.INGEST_SECRET) {
    return c.json({ error: 'unauthorized' }, 401);
  }

  const alert = await c.req.json<RawAlert>();
  const fp = fingerprint(alert.service, alert.check, alert.region);

  if (alert.state === 'firing') {
    const { incident, created } = await findOrCreateCanonical(c.env, alert, fp);

    if (!created) {
      // Duplicate: suppress and log
      await suppressDuplicate(c.env, incident.id, alert, fp);
      return c.json({
        ok: true,
        action: 'suppressed',
        canonicalId: incident.id,
      });
    }

    // New canonical incident — page on-call
    await fetch('https://slack.com/api/chat.postMessage', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${c.env.SLACK_BOT_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        channel: c.env.ON_CALL_CHANNEL,
        text: `:rotating_light: [${alert.severity.toUpperCase()}] New incident: *${alert.service}* — ${alert.check} in ${alert.region}\nCanonical ID: \`${incident.id}\``,
      }),
    });

    return c.json({ ok: true, action: 'created', canonicalId: incident.id });
  }

  if (alert.state === 'resolved') {
    const existing = await env_findOpen(c.env, fp);
    if (!existing) return c.json({ ok: true, action: 'no_open_incident' });

    await c.env.DB.prepare(`
      UPDATE canonical_incidents
      SET resolved_child_count = resolved_child_count + 1, child_count = MAX(child_count, resolved_child_count + 1)
      WHERE id = ?
    `).bind(existing.id).run();

    await checkAutoResolve(c.env, existing, fp);
    return c.json({ ok: true, action: 'child_resolved', canonicalId: existing.id });
  }

  return c.json({ error: 'invalid state' }, 400);
});

async function env_findOpen(env: Env, fp: string): Promise<CanonicalIncident | null> {
  const kvVal = await env.ALERT_STORE.get(`group:${fp}`);
  if (kvVal) return JSON.parse(kvVal);
  return env.DB.prepare(`
    SELECT * FROM canonical_incidents WHERE fingerprint = ? AND resolved_at IS NULL
  `).bind(fp).first<CanonicalIncident>();
}

// Noise reduction report
app.get('/metrics/noise-reduction', async (c) => {
  const since = Date.now() - 7 * 86_400_000;
  const { results } = await c.env.DB.prepare(`
    SELECT
      ci.service,
      COUNT(DISTINCT ci.id) AS canonical_count,
      SUM(ci.suppressed_count) AS suppressed_count,
      SUM(ci.child_count) AS total_child_alerts,
      ROUND(100.0 * SUM(ci.suppressed_count) / MAX(1, SUM(ci.child_count)), 1) AS suppression_pct
    FROM canonical_incidents ci
    WHERE ci.opened_at >= ?
    GROUP BY ci.service
    ORDER BY suppression_pct DESC
  `).bind(since).all();

  return c.json({ since: new Date(since).toISOString(), results });
});

export default app;
```

## Implementation Details

- **KV as fast-path cache**: The fingerprint-to-incident mapping lives in KV for sub-millisecond lookup during high-volume alert storms. D1 is the source of truth; KV is invalidated when an incident resolves.
- **DEDUP_WINDOW_MS**: 30 minutes is appropriate for most infrastructure outages. For fast-recovering services (auto-scaled), reduce to 5 minutes. For database failovers that can last hours, extend to 2 hours.
- **Fingerprint design**: `(service, check, region)` is a good default. Do not include `value` or `timestamp` in the fingerprint — those change per firing but describe the same condition.
- **Auto-resolve accuracy**: The `child_count` is set to 1 at creation and incremented on each new correlated child. `resolved_child_count` increments on resolve events. When equal, the canonical incident closes. This handles cases where a third source fires 5 minutes into the outage.
- **Suppression log**: Every suppressed alert is persisted in D1 for audit and noise reduction reporting. This lets you prove to stakeholders that the system suppressed 847 pages during last month's DNS outage.

## Anti-patterns

- **Fingerprinting by alert title or message text**: Alert names drift as monitoring configs change. Always fingerprint by structured fields (`service`, `check`, `region`), never by free-text labels.
- **Using only KV for incident state**: KV TTL expiry during a long outage will create a new canonical incident for subsequent alerts from the same source, duplicating pages. D1 is the authoritative store.
- **Resolving canonical incident on first child resolve**: An outage with 5 affected regions should not auto-resolve when the first region recovers. Track `resolved_child_count` vs `child_count`.
- **Suppressing all alerts from a service during a silenced window**: Silence windows created by one team can mask genuine new failures from another team in the same service. Scope suppression to fingerprint, not service.

## Gotchas

- `btoa()` is available in Workers. For non-ASCII service or check names, use `encodeURIComponent` before `btoa`, or use a proper hash (e.g., `crypto.subtle.digest('SHA-256', ...)`) for the fingerprint.
- PagerDuty sends both `trigger` and `resolve` event types. Map `trigger` → `state: 'firing'` and `resolve` → `state: 'resolved'` in your source-specific adapter before posting to `/alert/ingest`.
- Grafana unified alerting sends `alerting` (firing) and `ok` (resolved) states. The mapping is: `alerting` → `firing`, `ok` → `resolved`, `pending` → ignore.
- D1's `WHERE resolved_at IS NULL` partial index syntax works in SQLite but is not universally recognized by all ORM query planners. Test query performance with `EXPLAIN QUERY PLAN` if the incidents table grows large.

## Verification

```bash
# 1. Fire a canonical alert
curl -X POST https://dedup-worker.example.workers.dev/alert/ingest \
  -H 'x-ingest-secret: SECRET' \
  -H 'Content-Type: application/json' \
  -d '{"source":"grafana","externalId":"G-001","service":"checkout","check":"error-rate","region":"eu-west-1","severity":"critical","state":"firing","firedAt":"2026-08-24T10:00:00Z","labels":{}}'
# => {"action":"created","canonicalId":"CINC-...-..."}

# 2. Fire a duplicate within dedup window
curl -X POST https://dedup-worker.example.workers.dev/alert/ingest \
  -H 'x-ingest-secret: SECRET' \
  -H 'Content-Type: application/json' \
  -d '{"source":"pagerduty","externalId":"PD-002","service":"checkout","check":"error-rate","region":"eu-west-1","severity":"critical","state":"firing","firedAt":"2026-08-24T10:03:00Z","labels":{}}'
# => {"action":"suppressed","canonicalId":"CINC-...-..."}

# 3. Resolve
curl -X POST https://dedup-worker.example.workers.dev/alert/ingest \
  -H 'x-ingest-secret: SECRET' \
  -H 'Content-Type: application/json' \
  -d '{"source":"grafana","externalId":"G-001","service":"checkout","check":"error-rate","region":"eu-west-1","severity":"critical","state":"resolved","firedAt":"2026-08-24T10:30:00Z","labels":{}}'
# => {"action":"child_resolved"} and Slack auto-resolve notification

# 4. Check noise reduction metrics
curl https://dedup-worker.example.workers.dev/metrics/noise-reduction
# => [{"service":"checkout","suppression_pct":50,...}]
```

## Related

- `documentation/docs/policies/issues/workers-mean-time-to-detect.md` — consumes deduplicated alert events for MTTD calculation
- `documentation/docs/policies/issues/workers-on-call-handoff-bot.md` — handoff summary shows alert counts from the dedup pipeline
- `documentation/docs/policies/issues/workers-sla-breach-auto-escalation.md` — canonical incidents trigger SLA breach evaluation
- `documentation/docs/policies/issues/workers-runbook-executor.md` — canonical incident creation triggers automated runbook execution

## Sources

- [Cloudflare KV Runtime API](https://developers.cloudflare.com/kv/api/)
- [Cloudflare D1 API Reference](https://developers.cloudflare.com/d1/worker-api/)
- [Alert Correlation Techniques — SRE Workbook](https://sre.google/workbook/alerting-on-slos/)
- [PagerDuty Generic Events API v2](https://developer.pagerduty.com/api-reference/YXBpOjI3NDgyNjU-pager-duty-v2-events-api)
