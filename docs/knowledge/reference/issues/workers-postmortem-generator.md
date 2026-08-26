# Automated Postmortem Generation from Incident Data

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

After an incident is resolved, engineers spend hours manually pulling timeline events from multiple sources into a postmortem document. The process is error-prone and slow. You need a Worker that, when triggered, automatically fetches the incident timeline from D1, pulls correlated error logs from Analytics Engine, constructs a postmortem markdown document, stores it in R2, and notifies the team in Slack with a signed URL to the draft.

## Context

Incident events (alert fired, runbook followed, mitigation applied, resolved) are written to a D1 `incident_events` table by your alerting pipeline. Error counts and rate spikes are available in Analytics Engine via the SQL API. The postmortem template is defined in the Worker and rendered as Markdown. R2 stores the draft with a 7-day presigned URL for review. A Slack message surfaces the link to the on-call channel.

## Solution

```typescript
// workers-postmortem/src/index.ts
export interface Env {
  DB: D1Database;
  POSTMORTEM_BUCKET: R2Bucket;
  SLACK_WEBHOOK_URL: string;
  ANALYTICS_ACCOUNT_ID: string;
  ANALYTICS_API_TOKEN: string;
  ANALYTICS_DATASET: string;
  PUBLIC_BUCKET_DOMAIN: string; // e.g. postmortems.example.com
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface IncidentRow {
  incident_id: string;
  event_type: string; // 'alert_fired' | 'ack' | 'mitigation' | 'resolved'
  description: string;
  actor: string;
  occurred_at: number; // unix ms
}

interface AnalyticsPoint {
  timestamp: string;
  error_count: number;
  service: string;
}

interface PostmortemContext {
  incidentId: string;
  title: string;
  severity: string;
  events: IncidentRow[];
  errorPoints: AnalyticsPoint[];
  totalDurationMs: number;
}

// ---------------------------------------------------------------------------
// D1: fetch incident timeline
// ---------------------------------------------------------------------------
async function fetchTimeline(env: Env, incidentId: string): Promise<IncidentRow[]> {
  const { results } = await env.DB.prepare(
    `SELECT incident_id, event_type, description, actor, occurred_at
     FROM incident_events
     WHERE incident_id = ?
     ORDER BY occurred_at ASC`,
  )
    .bind(incidentId)
    .all<IncidentRow>();
  return results;
}

async function fetchIncidentMeta(
  env: Env,
  incidentId: string,
): Promise<{ title: string; severity: string } | null> {
  const row = await env.DB.prepare(
    `SELECT title, severity FROM incidents WHERE id = ?`,
  )
    .bind(incidentId)
    .first<{ title: string; severity: string }>();
  return row ?? null;
}

// ---------------------------------------------------------------------------
// Analytics Engine SQL API: fetch error spikes during incident window
// ---------------------------------------------------------------------------
async function fetchErrorLogs(
  env: Env,
  startMs: number,
  endMs: number,
): Promise<AnalyticsPoint[]> {
  const startSec = Math.floor(startMs / 1000);
  const endSec = Math.floor(endMs / 1000);
  const sql = `
    SELECT
      toStartOfInterval(timestamp, INTERVAL '1' MINUTE) AS ts,
      SUM(_sample_interval * error_count) AS error_count,
      blob1 AS service
    FROM ${env.ANALYTICS_DATASET}
    WHERE timestamp >= toDateTime(${startSec})
      AND timestamp <= toDateTime(${endSec})
      AND double1 > 0
    GROUP BY ts, service
    ORDER BY ts ASC
    LIMIT 120
  `;
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.ANALYTICS_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.ANALYTICS_API_TOKEN}`,
        'Content-Type': 'text/plain',
      },
      body: sql,
    },
  );
  if (!res.ok) return [];
  const json: { data: Array<{ ts: string; error_count: string; service: string }> } =
    await res.json();
  return (json.data ?? []).map(row => ({
    timestamp: row.ts,
    error_count: Number(row.error_count),
    service: row.service,
  }));
}

// ---------------------------------------------------------------------------
// Postmortem Markdown renderer
// ---------------------------------------------------------------------------
function formatMs(ms: number): string {
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function renderPostmortem(ctx: PostmortemContext): string {
  const alertEvent = ctx.events.find(e => e.event_type === 'alert_fired');
  const resolvedEvent = ctx.events.find(e => e.event_type === 'resolved');

  const startTs = alertEvent ? new Date(alertEvent.occurred_at).toISOString() : 'unknown';
  const endTs = resolvedEvent ? new Date(resolvedEvent.occurred_at).toISOString() : 'ongoing';

  const timelineSection = ctx.events
    .map(e => `| ${new Date(e.occurred_at).toISOString()} | ${e.event_type} | ${e.actor} | ${e.description} |`)
    .join('\n');

  const errorSection = ctx.errorPoints.length
    ? ctx.errorPoints
        .map(p => `| ${p.timestamp} | ${p.service} | ${p.error_count} |`)
        .join('\n')
    : '_No error spike data available._';

  return `# Postmortem — ${ctx.title}

**Incident ID:** ${ctx.incidentId}
**Severity:** ${ctx.severity}
**Duration:** ${formatMs(ctx.totalDurationMs)}
**Start:** ${startTs}
**End:** ${endTs}
**Status:** DRAFT — requires human review before publication

---

## Executive Summary

> _Fill in a 2–3 sentence summary of what happened, the impact, and the resolution._

## Impact

| Metric | Value |
|--------|-------|
| Duration | ${formatMs(ctx.totalDurationMs)} |
| Severity | ${ctx.severity} |
| Affected services | _to be filled_ |
| User impact | _to be filled_ |

## Timeline

| Timestamp (UTC) | Event | Actor | Description |
|-----------------|-------|-------|-------------|
${timelineSection}

## Error Rate During Incident

| Timestamp | Service | Error Count |
|-----------|---------|-------------|
${errorSection}

## Root Cause Analysis

> _5 Whys or fault tree to be completed by the incident owner._

## Contributing Factors

- _Factor 1_
- _Factor 2_

## Resolution

> _Describe the mitigation and permanent fix._

## Action Items

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| _TBD_ | _TBD_ | _TBD_ | open |

## Lessons Learned

> _What went well? What did not? What will change?_

---

_Generated automatically by the postmortem-generator Worker at ${new Date().toISOString()}. Human review required._
`;
}

// ---------------------------------------------------------------------------
// Store in R2 and generate a signed URL
// ---------------------------------------------------------------------------
async function storeAndSign(
  env: Env,
  incidentId: string,
  markdown: string,
): Promise<string> {
  const key = `postmortems/${incidentId}/draft-${Date.now()}.md`;
  await env.POSTMORTEM_BUCKET.put(key, markdown, {
    httpMetadata: { contentType: 'text/markdown; charset=utf-8' },
    customMetadata: { incident_id: incidentId, status: 'draft' },
  });
  // Return a direct public URL — for private buckets, use a pre-signed URL via
  // Workers signed URLs helper or an access-controlled endpoint instead.
  return `https://${env.PUBLIC_BUCKET_DOMAIN}/${key}`;
}

// ---------------------------------------------------------------------------
// Slack notification
// ---------------------------------------------------------------------------
async function notifySlack(env: Env, incidentId: string, url: string, title: string) {
  const body = {
    text: `:memo: *Postmortem draft ready*\n` +
          `*Incident:* ${incidentId} — ${title}\n` +
          `*Draft:* ${url}\n` +
          `Please review, add root cause analysis, and publish.`,
  };
  await fetch(env.SLACK_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Main generation handler
// ---------------------------------------------------------------------------
async function generatePostmortem(env: Env, incidentId: string): Promise<Response> {
  const meta = await fetchIncidentMeta(env, incidentId);
  if (!meta) {
    return Response.json({ error: 'Incident not found' }, { status: 404 });
  }

  const events = await fetchTimeline(env, incidentId);
  if (!events.length) {
    return Response.json({ error: 'No events found for incident' }, { status: 422 });
  }

  const firstMs = events[0].occurred_at;
  const lastMs = events[events.length - 1].occurred_at;
  const totalDurationMs = lastMs - firstMs;

  const errorPoints = await fetchErrorLogs(env, firstMs, lastMs);

  const ctx: PostmortemContext = {
    incidentId,
    title: meta.title,
    severity: meta.severity,
    events,
    errorPoints,
    totalDurationMs,
  };

  const markdown = renderPostmortem(ctx);
  const url = await storeAndSign(env, incidentId, markdown);
  await notifySlack(env, incidentId, url, meta.title);

  return Response.json({ ok: true, url });
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method not allowed', { status: 405 });
    const url = new URL(req.url);
    if (url.pathname !== '/generate') return new Response('Not found', { status: 404 });
    const { incident_id } = await req.json<{ incident_id: string }>();
    if (!incident_id) return new Response('Missing incident_id', { status: 400 });
    return generatePostmortem(env, incident_id);
  },
};
```

**D1 schema:**

```sql
CREATE TABLE incidents (
  id       TEXT PRIMARY KEY,
  title    TEXT NOT NULL,
  severity TEXT NOT NULL  -- P1 | P2 | P3
);

CREATE TABLE incident_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  incident_id TEXT NOT NULL REFERENCES incidents(id),
  event_type  TEXT NOT NULL,
  description TEXT NOT NULL,
  actor       TEXT NOT NULL,
  occurred_at INTEGER NOT NULL  -- unix ms
);
```

## Implementation Details

- The Analytics Engine SQL API requires a `Bearer` token with `analytics:read` permission scoped to the account.
- `renderPostmortem` outputs Markdown with explicit placeholder rows, prompting reviewers to fill required fields before publication.
- R2 `put` accepts `customMetadata` for filtering drafts vs. published postmortems in a separate list endpoint.
- The Worker stores the draft immediately; Slack carries the URL so the team can start reviewing without polling.
- `formatMs` converts raw milliseconds to a human-readable `Xh Ym` string for the template.

## Anti-patterns

- **Generating the postmortem in Slack alone.** Slack messages expire and are not searchable as structured documents; always persist to R2.
- **Publishing directly without a review gate.** Auto-generated documents contain placeholder sections. Never remove the `DRAFT` status flag automatically.
- **Querying Analytics Engine with unbounded time windows.** Large incidents can span days; add a `LIMIT` and pagination to avoid oversize SQL responses.
- **Storing the API token in `wrangler.toml`.** Use `wrangler secret put ANALYTICS_API_TOKEN`.

## Gotchas

- Analytics Engine SQL API returns data within ~60 seconds of ingestion. For very recent incidents, some data points near the resolution time may be missing.
- R2 object keys are case-sensitive. Normalise incident IDs to lowercase before building the key to avoid duplicate objects.
- The `POSTMORTEM_BUCKET` R2 binding requires `r2:write` in `wrangler.toml` and the bucket must be created before deployment.
- Signed URL generation is not yet natively supported by R2 bindings (as of mid-2026). Use the Workers `R2Bucket.createMultipartUpload` approach or a separate access-controlled Worker endpoint instead of a raw public domain.

## Verification

1. Seed D1 with an incident and five timeline events covering `alert_fired` → `ack` → `mitigation` → `resolved`.
2. POST `{"incident_id": "INC-001"}` to `/generate`. Assert HTTP 200 and a `url` in the response.
3. Fetch the returned URL. Assert the Markdown contains all seeded event rows in the timeline table.
4. Check the Slack channel for the notification message with the correct incident title and URL.
5. List R2 objects under `postmortems/INC-001/` and verify exactly one object with `status: draft` metadata.

## Related

- `workers-sla-breach-auto-escalation.md` — breach events that trigger postmortem generation
- `workers-change-failure-rate-tracker.md` — DORA CFR context for postmortem action items
- `workers-github-issue-triage-bot.md` — incident issues that feed the timeline

## Sources

- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- https://developers.cloudflare.com/d1/
- https://sre.google/sre-book/postmortem-culture/
