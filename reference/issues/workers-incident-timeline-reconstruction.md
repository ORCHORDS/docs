# Automatic Incident Timeline Reconstruction in Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After an incident, engineers spend hours manually piecing together what happened and when: which deploy went out, when did the error rate spike, which alert fired first, who was paged? Without a reconstruction tool, postmortems are incomplete, causal chains are guessed rather than proven, and the same failure modes recur because the timeline was never correctly understood.

## Context

A Cloudflare Worker can aggregate events from disparate sources — deployment webhooks (GitHub Actions, Wrangler), alert ingest (Grafana, PagerDuty), anomaly detection (AE anomaly annotations), and on-call page records — and reconstruct a chronological timeline for any incident. It stores the timeline in D1, performs lightweight causal analysis (did a deploy immediately precede the error spike?), and serves an exportable JSON suitable for postmortem templates.

Prerequisites:
- D1 database bound as `DB`
- KV namespace bound as `TIMELINE_CACHE`
- Deployment webhooks configured to POST to `/event/deploy`
- Alert sources (Grafana, PagerDuty) posting to `/event/alert`
- On-call system posting page records to `/event/page`

## Solution

```typescript
// worker-timeline.ts
import { Hono } from 'hono';

export interface Env {
  DB: D1Database;
  TIMELINE_CACHE: KVNamespace;
  INGEST_SECRET: string;
}

type EventKind = 'deploy' | 'alert' | 'anomaly' | 'page' | 'manual_note';

interface TimelineEvent {
  id: string;
  incidentId: string;
  kind: EventKind;
  happenedAt: number; // epoch ms
  source: string;
  title: string;
  detail: Record<string, unknown>;
  causalScore?: number; // 0-1, how likely to be the root cause
  createdAt: number;
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS timeline_events (
  id TEXT PRIMARY KEY,
  incident_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  happened_at INTEGER NOT NULL,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  detail TEXT NOT NULL,
  causal_score REAL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tl_incident ON timeline_events(incident_id, happened_at);
CREATE TABLE IF NOT EXISTS incidents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  started_at INTEGER NOT NULL,
  resolved_at INTEGER,
  created_at INTEGER NOT NULL
);
`;

const app = new Hono<{ Bindings: Env }>();

app.post('/init', async (c) => {
  for (const stmt of SCHEMA.split(';').map(s => s.trim()).filter(Boolean)) {
    await c.env.DB.prepare(stmt).run();
  }
  return c.json({ ok: true });
});

// --- incident registration ---
app.post('/incident', async (c) => {
  const { title, startedAt } = await c.req.json<{ title: string; startedAt: string }>();
  const id = `INC-${Date.now()}`;
  await c.env.DB.prepare(`
    INSERT INTO incidents (id, title, started_at, created_at) VALUES (?, ?, ?, ?)
  `).bind(id, title, new Date(startedAt).getTime(), Date.now()).run();
  return c.json({ id });
});

// --- generic event ingest ---
async function ingestEvent(
  env: Env,
  incidentId: string,
  kind: EventKind,
  happenedAt: number,
  source: string,
  title: string,
  detail: Record<string, unknown>
): Promise<string> {
  const id = crypto.randomUUID();
  await env.DB.prepare(`
    INSERT INTO timeline_events
      (id, incident_id, kind, happened_at, source, title, detail, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(id, incidentId, kind, happenedAt, source, title, JSON.stringify(detail), Date.now()).run();

  // Invalidate cached timeline for this incident
  await env.TIMELINE_CACHE.delete(`timeline:${incidentId}`);
  return id;
}

app.post('/event/deploy', async (c) => {
  if (c.req.header('x-ingest-secret') !== c.env.INGEST_SECRET) return c.json({ error: 'unauthorized' }, 401);
  const { incidentId, service, commitSha, deployedBy, deployedAt, environment } =
    await c.req.json<{
      incidentId: string; service: string; commitSha: string;
      deployedBy: string; deployedAt: string; environment: string;
    }>();

  const id = await ingestEvent(
    c.env, incidentId, 'deploy',
    new Date(deployedAt).getTime(),
    'github-actions',
    `Deploy ${service}@${commitSha.slice(0, 7)} to ${environment}`,
    { service, commitSha, deployedBy, environment }
  );
  return c.json({ ok: true, id });
});

app.post('/event/alert', async (c) => {
  if (c.req.header('x-ingest-secret') !== c.env.INGEST_SECRET) return c.json({ error: 'unauthorized' }, 401);
  const { incidentId, alertName, source, severity, firedAt, labels } =
    await c.req.json<{
      incidentId: string; alertName: string; source: string;
      severity: string; firedAt: string; labels: Record<string, string>;
    }>();

  const id = await ingestEvent(
    c.env, incidentId, 'alert',
    new Date(firedAt).getTime(),
    source,
    `[${severity.toUpperCase()}] ${alertName}`,
    { alertName, severity, labels }
  );
  return c.json({ ok: true, id });
});

app.post('/event/page', async (c) => {
  if (c.req.header('x-ingest-secret') !== c.env.INGEST_SECRET) return c.json({ error: 'unauthorized' }, 401);
  const { incidentId, engineer, pagedAt, source } =
    await c.req.json<{ incidentId: string; engineer: string; pagedAt: string; source: string }>();

  const id = await ingestEvent(
    c.env, incidentId, 'page',
    new Date(pagedAt).getTime(),
    source,
    `On-call paged: ${engineer}`,
    { engineer }
  );
  return c.json({ ok: true, id });
});

// --- timeline retrieval with causal analysis ---
app.get('/incident/:id/timeline', async (c) => {
  const incidentId = c.req.param('id');

  // Serve from cache if available
  const cached = await c.env.TIMELINE_CACHE.get(`timeline:${incidentId}`);
  if (cached) return c.json(JSON.parse(cached));

  const { results: events } = await c.env.DB.prepare(`
    SELECT * FROM timeline_events
    WHERE incident_id = ?
    ORDER BY happened_at ASC
  `).bind(incidentId).all<{
    id: string; kind: string; happened_at: number; source: string;
    title: string; detail: string; causal_score: number;
  }>();

  // Causal analysis: deploys within 10 minutes before the first alert
  const firstAlert = events.find(e => e.kind === 'alert');
  const CAUSAL_WINDOW_MS = 10 * 60 * 1000;

  const enriched = events.map(e => {
    let causalScore = 0;
    if (e.kind === 'deploy' && firstAlert) {
      const lag = firstAlert.happened_at - e.happened_at;
      if (lag > 0 && lag <= CAUSAL_WINDOW_MS) {
        // Linear decay: deploy right before alert gets score 1.0
        causalScore = 1 - lag / CAUSAL_WINDOW_MS;
      }
    }
    return {
      ...e,
      detail: JSON.parse(e.detail),
      causalScore: Math.round(causalScore * 100) / 100,
      happenedAt: new Date(e.happened_at).toISOString(),
    };
  });

  const suspectDeploy = enriched
    .filter(e => e.kind === 'deploy')
    .sort((a, b) => b.causalScore - a.causalScore)[0] ?? null;

  const result = {
    incidentId,
    generatedAt: new Date().toISOString(),
    eventCount: enriched.length,
    likelyCause: suspectDeploy
      ? { title: suspectDeploy.title, score: suspectDeploy.causalScore }
      : null,
    timeline: enriched,
  };

  // Cache for 5 minutes; invalidated on new event ingest
  await c.env.TIMELINE_CACHE.put(`timeline:${incidentId}`, JSON.stringify(result), {
    expirationTtl: 300,
  });

  return c.json(result);
});

// --- exportable JSON for postmortem ---
app.get('/incident/:id/timeline/export', async (c) => {
  const incidentId = c.req.param('id');
  const resp = await app.fetch(
    new Request(`https://internal/incident/${incidentId}/timeline`),
    c.env
  );
  const data = await resp.json();
  return new Response(JSON.stringify(data, null, 2), {
    headers: {
      'Content-Type': 'application/json',
      'Content-Disposition': `attachment; filename="timeline-${incidentId}.json"`,
    },
  });
});

export default app;
```

## Implementation Details

- **Causal scoring**: The linear decay function assigns score 1.0 to a deploy that happened 0 ms before the first alert, and 0.0 to one that happened exactly 10 minutes before. Multiple suspect deploys are ranked; the highest-scoring one surfaces as `likelyCause`.
- **Cache invalidation**: Every event ingest deletes the KV cache entry for that incident's timeline. Reads are served from cache for 5 minutes after the last write, keeping D1 reads low during active incidents.
- **Postmortem export**: The `/export` endpoint returns a downloadable JSON file with the full enriched timeline. Postmortem templates can reference `likelyCause.title` directly.
- **Manual notes**: `kind: 'manual_note'` events can be added by engineers via a direct D1 insert or a simple POST wrapper, allowing human context ("DB failover initiated") to appear inline in the timeline.
- **Incident window**: Events are associated with an incident by `incidentId`; there is no automatic windowing. For auto-correlation by time window, add a query that pulls all events within ±15 minutes of the incident's `started_at`.

## Anti-patterns

- **Using wall-clock times from different sources without normalization**: PagerDuty uses UTC, but some GitHub Actions runners have misconfigured clocks. Always validate that `happenedAt` is within a plausible range (not in the future, not before 2020) before inserting.
- **Rebuilding the timeline on every postmortem dashboard refresh**: Cache aggressively. The timeline for a resolved incident never changes; set KV TTL to 7 days post-resolution.
- **Treating causal score as definitive root cause**: It is a heuristic, not a proof. A deploy with score 0.9 preceded the alert but may be unrelated. Always include the score as a signal, not a conclusion.
- **Storing `detail` as separate columns**: The `detail TEXT` (JSON blob) pattern keeps the schema flexible as event shapes vary per source. Resist normalizing prematurely.

## Gotchas

- D1's `TEXT` type for JSON blobs is correct — D1 does not have a native JSON column type. Use `JSON.stringify` on write and `JSON.parse` on read consistently.
- The `/export` route calls `app.fetch` with an internal URL. In production, route it through the actual Worker URL or refactor the timeline logic into a shared function to avoid the internal-URL pattern.
- GitHub Actions sends deployment webhooks on `deployment_status` events (not `deployment`). Wait for status `success` before posting to `/event/deploy`.
- AE anomaly detection timestamps may lag the actual anomaly by 2–5 minutes due to evaluation windows. Account for this by subtracting the evaluation period from `happenedAt` when ingesting anomaly events.

## Verification

```bash
# 1. Create incident
curl -X POST https://timeline-worker.example.workers.dev/incident \
  -H 'Content-Type: application/json' \
  -d '{"title": "Checkout latency spike", "startedAt": "2026-08-24T14:00:00Z"}'
# => {"id":"INC-1724508000000"}

# 2. Ingest a deploy (9 minutes before alert = causal score ~0.1)
curl -X POST https://timeline-worker.example.workers.dev/event/deploy \
  -H 'x-ingest-secret: SECRET' \
  -H 'Content-Type: application/json' \
  -d '{"incidentId":"INC-1724508000000","service":"checkout","commitSha":"abc1234","deployedBy":"ci-bot","deployedAt":"2026-08-24T13:51:00Z","environment":"production"}'

# 3. Ingest alert
curl -X POST https://timeline-worker.example.workers.dev/event/alert \
  -H 'x-ingest-secret: SECRET' \
  -H 'Content-Type: application/json' \
  -d '{"incidentId":"INC-1724508000000","alertName":"HighLatency","source":"grafana","severity":"critical","firedAt":"2026-08-24T14:00:00Z","labels":{"service":"checkout"}}'

# 4. Retrieve timeline
curl https://timeline-worker.example.workers.dev/incident/INC-1724508000000/timeline
# => {likelyCause: {title: "Deploy checkout@abc1234...", score: 0.1}, timeline: [...]}

# 5. Export for postmortem
curl -o timeline-export.json \
  https://timeline-worker.example.workers.dev/incident/INC-1724508000000/timeline/export
```

## Related

- `documentation/categories/issues/workers-postmortem-generator.md` — consumes timeline export JSON to draft postmortem documents
- `documentation/categories/issues/workers-mean-time-to-detect.md` — alert timestamps fed into this timeline drive MTTD calculations
- `documentation/categories/issues/workers-change-failure-rate-tracker.md` — deploy events in timeline feed change failure rate metrics
- `documentation/categories/issues/workers-incident-response-bot.md` — bot that triggers timeline reconstruction automatically on incident open

## Sources

- [Cloudflare D1 Documentation](https://developers.cloudflare.com/d1/)
- [Cloudflare KV Documentation](https://developers.cloudflare.com/kv/)
- [GitHub Deployment Events](https://docs.github.com/en/developers/webhooks-and-events/webhooks/webhook-events-and-payloads#deployment_status)
- [SRE Workbook — Incident Management](https://sre.google/workbook/incident-response/)
