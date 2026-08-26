# Public Status Page Powered by Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your ops team gets DMs from customers asking "is the API down?" before your alerting even triggers. You need a public-facing status page that runs health checks on each service endpoint every minute, shows live operational status, exposes a machine-readable JSON API for status badges, and publishes an Atom feed so power users can subscribe to incidents — all served from a single Worker with zero third-party dependencies.

## Context

The page is built from three concerns:

1. **Data collection** — a scheduled Worker pings each service endpoint and writes the result to D1.
2. **Aggregation** — a Worker route reads D1 to compute current status per service and 90-day incident history.
3. **Presentation** — HTML status page, `/api/status.json` badge endpoint, and `/feed/atom.xml`.

Stack:
- **D1** — `checks` table (ts, service, url, ok, latency_ms, status_code) + `incidents` table
- **KV** — cached rendered HTML and JSON to survive D1 connection spikes
- **Workers Static Assets** — serve the CSS/JS shell; Worker populates the data layer

## Solution

```typescript
// status-page.ts
import type { D1Database, KVNamespace, Fetcher } from '@cloudflare/workers-types';

export interface Env {
  DB: D1Database;
  STATUS_KV: KVNamespace;
  ASSETS: Fetcher;
  CHECK_TIMEOUT_MS: string;   // default "5000"
  CACHE_TTL_SECONDS: string;  // default "30"
}

// ── service registry ──────────────────────────────────────────────────────────

const SERVICES: Array<{ id: string; name: string; url: string }> = [
  { id: 'api',       name: 'REST API',         url: 'https://api.example.com/health' },
  { id: 'web',       name: 'Web App',           url: 'https://example.com/_health'   },
  { id: 'auth',      name: 'Auth Service',      url: 'https://auth.example.com/ping' },
  { id: 'cdn',       name: 'CDN / Assets',      url: 'https://cdn.example.com/health'},
  { id: 'ws',        name: 'WebSocket Gateway', url: 'https://ws.example.com/health' },
];

// ── types ─────────────────────────────────────────────────────────────────────

type OperationalStatus = 'operational' | 'degraded' | 'outage' | 'unknown';

interface ServiceStatus {
  id: string;
  name: string;
  status: OperationalStatus;
  latencyMs: number | null;
  checkedAt: number;
}

interface StatusPayload {
  page: { status: OperationalStatus; updatedAt: string };
  services: ServiceStatus[];
}

interface IncidentRow {
  id: number;
  service_id: string;
  started_at: number;
  resolved_at: number | null;
  description: string;
}

// ── health probe ──────────────────────────────────────────────────────────────

async function probe(
  service: (typeof SERVICES)[number],
  timeoutMs: number
): Promise<{ ok: boolean; latencyMs: number; statusCode: number }> {
  const start = Date.now();
  try {
    const res = await Promise.race([
      fetch(service.url, { method: 'GET', headers: { 'User-Agent': 'orchords-statusbot/1.0' } }),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), timeoutMs)
      ),
    ]);
    const latencyMs = Date.now() - start;
    return { ok: res.ok, latencyMs, statusCode: res.status };
  } catch {
    return { ok: false, latencyMs: Date.now() - start, statusCode: 0 };
  }
}

// ── scheduled: run checks ─────────────────────────────────────────────────────

async function runChecks(env: Env, ctx: ExecutionContext): Promise<void> {
  const timeoutMs = parseInt(env.CHECK_TIMEOUT_MS ?? '5000', 10);
  const now = Math.floor(Date.now() / 1000);

  const results = await Promise.all(
    SERVICES.map(async (svc) => {
      const r = await probe(svc, timeoutMs);
      return { ...svc, ...r, ts: now };
    })
  );

  // Batch-insert check results.
  const stmt = env.DB.prepare(
    `INSERT INTO checks (ts, service_id, url, ok, latency_ms, status_code)
     VALUES (?, ?, ?, ?, ?, ?)`
  );
  await env.DB.batch(
    results.map((r) =>
      stmt.bind(r.ts, r.id, r.url, r.ok ? 1 : 0, r.latencyMs, r.statusCode)
    )
  );

  // Auto-open incidents: 3 consecutive failures → create incident if none open.
  for (const svc of results.filter((r) => !r.ok)) {
    const recentFails = await env.DB
      .prepare(
        `SELECT COUNT(*) as cnt FROM checks
         WHERE service_id = ? AND ok = 0 AND ts >= ?`
      )
      .bind(svc.id, now - 180)
      .first<{ cnt: number }>();

    if ((recentFails?.cnt ?? 0) >= 3) {
      const open = await env.DB
        .prepare(
          `SELECT id FROM incidents
           WHERE service_id = ? AND resolved_at IS NULL LIMIT 1`
        )
        .bind(svc.id)
        .first<{ id: number }>();

      if (!open) {
        await env.DB
          .prepare(
            `INSERT INTO incidents (service_id, started_at, description)
             VALUES (?, ?, ?)`
          )
          .bind(svc.id, now, `Automated: ${svc.name} failing health checks`)
          .run();
      }
    }
  }

  // Auto-resolve incidents: all recent checks passing.
  for (const svc of results.filter((r) => r.ok)) {
    const recentPass = await env.DB
      .prepare(
        `SELECT COUNT(*) as cnt FROM checks
         WHERE service_id = ? AND ok = 1 AND ts >= ?`
      )
      .bind(svc.id, now - 180)
      .first<{ cnt: number }>();

    if ((recentPass?.cnt ?? 0) >= 3) {
      await env.DB
        .prepare(
          `UPDATE incidents SET resolved_at = ?
           WHERE service_id = ? AND resolved_at IS NULL`
        )
        .bind(now, svc.id)
        .run();
    }
  }

  // Bust the KV cache so the next request gets fresh data.
  ctx.waitUntil(
    Promise.all([
      env.STATUS_KV.delete('cache:status.json'),
      env.STATUS_KV.delete('cache:index.html'),
    ])
  );
}

// ── compute current status ────────────────────────────────────────────────────

async function currentStatus(db: D1Database): Promise<StatusPayload> {
  const now = Math.floor(Date.now() / 1000);

  const services: ServiceStatus[] = await Promise.all(
    SERVICES.map(async (svc) => {
      const row = await db
        .prepare(
          `SELECT ok, latency_ms, ts FROM checks
           WHERE service_id = ? ORDER BY ts DESC LIMIT 1`
        )
        .bind(svc.id)
        .first<{ ok: number; latency_ms: number; ts: number }>();

      if (!row) return { id: svc.id, name: svc.name, status: 'unknown' as const, latencyMs: null, checkedAt: 0 };

      // Degrade if p95 latency over last 5 min > 2 s.
      const p95Row = await db
        .prepare(
          `SELECT latency_ms FROM checks
           WHERE service_id = ? AND ts >= ?
           ORDER BY latency_ms DESC
           LIMIT 1 OFFSET CAST(0.05 * (SELECT COUNT(*) FROM checks WHERE service_id = ? AND ts >= ?) AS INTEGER)`
        )
        .bind(svc.id, now - 300, svc.id, now - 300)
        .first<{ latency_ms: number }>();

      let status: OperationalStatus = row.ok ? 'operational' : 'outage';
      if (status === 'operational' && (p95Row?.latency_ms ?? 0) > 2000) {
        status = 'degraded';
      }

      return {
        id: svc.id,
        name: svc.name,
        status,
        latencyMs: row.latency_ms,
        checkedAt: row.ts,
      };
    })
  );

  const worstStatus = services.reduce<OperationalStatus>((worst, s) => {
    const rank: Record<OperationalStatus, number> = { operational: 0, degraded: 1, outage: 2, unknown: 0 };
    return rank[s.status] > rank[worst] ? s.status : worst;
  }, 'operational');

  return {
    page: { status: worstStatus, updatedAt: new Date().toISOString() },
    services,
  };
}

// ── Atom feed ─────────────────────────────────────────────────────────────────

async function buildAtomFeed(db: D1Database): Promise<string> {
  const cutoff = Math.floor(Date.now() / 1000) - 90 * 86400;
  const rows = await db
    .prepare(
      `SELECT i.*, s.name AS service_name FROM incidents i
       LEFT JOIN services s ON s.id = i.service_id
       WHERE i.started_at >= ? ORDER BY i.started_at DESC LIMIT 50`
    )
    .bind(cutoff)
    .all<IncidentRow & { service_name: string }>();

  const entries = rows.results
    .map((inc) => {
      const start = new Date(inc.started_at * 1000).toISOString();
      const end = inc.resolved_at
        ? new Date(inc.resolved_at * 1000).toISOString()
        : 'Ongoing';
      return `  <entry>
    <id>https://status.example.com/incidents/${inc.id}</id>
    <title>${inc.service_name ?? inc.service_id}: ${inc.description}</title>
    <updated>${start}</updated>
    <summary>Started: ${start} | Resolved: ${end}</summary>
  </entry>`;
    })
    .join('\n');

  return `<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Orchords Status Incidents</title>
  <link href="https://status.example.com/"/>
  <updated>${new Date().toISOString()}</updated>
  <id>https://status.example.com/feed/atom.xml</id>
${entries}
</feed>`;
}

// ── fetch handler ─────────────────────────────────────────────────────────────

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    await runChecks(env, ctx);
  },

  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const cacheTtl = parseInt(env.CACHE_TTL_SECONDS ?? '30', 10);

    // JSON status API.
    if (url.pathname === '/api/status.json') {
      const cached = await env.STATUS_KV.get('cache:status.json');
      if (cached) return new Response(cached, { headers: { 'Content-Type': 'application/json', 'Cache-Control': `public, max-age=${cacheTtl}` } });
      const payload = await currentStatus(env.DB);
      const json = JSON.stringify(payload);
      ctx.waitUntil(env.STATUS_KV.put('cache:status.json', json, { expirationTtl: cacheTtl }));
      return new Response(json, { headers: { 'Content-Type': 'application/json', 'Cache-Control': `public, max-age=${cacheTtl}` } });
    }

    // Atom feed.
    if (url.pathname === '/feed/atom.xml') {
      const feed = await buildAtomFeed(env.DB);
      return new Response(feed, { headers: { 'Content-Type': 'application/atom+xml; charset=utf-8' } });
    }

    // 90-day incident history JSON.
    if (url.pathname === '/api/incidents') {
      const cutoff = Math.floor(Date.now() / 1000) - 90 * 86400;
      const rows = await env.DB
        .prepare(`SELECT * FROM incidents WHERE started_at >= ? ORDER BY started_at DESC`)
        .bind(cutoff)
        .all<IncidentRow>();
      return Response.json({ incidents: rows.results });
    }

    // Fall through to static asset (HTML shell).
    return env.ASSETS.fetch(request);
  },
};
```

## Implementation Details

**D1 schema** — two tables: `checks (ts INTEGER, service_id TEXT, url TEXT, ok INTEGER, latency_ms INTEGER, status_code INTEGER)` and `incidents (id INTEGER PRIMARY KEY AUTOINCREMENT, service_id TEXT, started_at INTEGER, resolved_at INTEGER, description TEXT)`. Index both on `(service_id, ts DESC)` for sub-millisecond lookups.

**Automatic incident lifecycle** — the scheduled handler opens an incident after 3 consecutive failures (3 minutes) and resolves it after 3 consecutive passes. This avoids transient 1-second blips creating incidents while ensuring real outages are captured promptly.

**p95 degradation detection** — the `OFFSET` trick in the p95 query (`LIMIT 1 OFFSET 0.05 * count`) uses SQLite's ordering to find the 95th-percentile latency without a full table scan. For correctness it works on a 5-minute sliding window.

**KV HTML cache** — the rendered HTML is cached in KV for 30 seconds. The scheduled cron busts the cache after each check run so the page reflects the latest state without users ever seeing stale "operational" banners.

## Anti-patterns

- **Hosting the status page on the monitored infrastructure**: if your main domain goes down, the status page must still be reachable. Workers run on the CF edge, fully independent of your origin servers.
- **Single-check incident creation**: one failed check fires immediately even during deploys. Require 3 consecutive failures over 3 minutes before opening an incident.
- **Omitting the Atom feed**: status badges are machine-readable but don't notify subscribers. The Atom feed lets engineers subscribe in Slack (`/feed subscribe`) or their RSS reader.

## Gotchas

- **`fetch` inside a scheduled handler**: the outbound `fetch` calls to service endpoints count against your Worker's subrequest budget (1000/invocation). With 5 services that leaves 995 for D1 calls — more than enough, but audit if you add many more services.
- **D1 connection limits**: a Worker instance shares D1 connections. Parallelise probes with `Promise.all`, but batch the D1 inserts with `db.batch()` rather than individual awaited statements.
- **SQLite `OFFSET` float coercion**: `CAST(0.05 * count AS INTEGER)` is required — SQLite will silently treat a float OFFSET as an error in some versions.

## Verification

```bash
# Trigger a manual scheduled run.
npx wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*+*+*+*+*"

# Validate JSON API.
curl -s https://status.example.com/api/status.json | jq '.page.status'

# Validate Atom feed.
curl -s https://status.example.com/feed/atom.xml | xmllint --noout -

# Query D1 for latest check results.
npx wrangler d1 execute <DB_NAME> \
  --command "SELECT service_id, ok, latency_ms FROM checks ORDER BY ts DESC LIMIT 10;"
```

## Related

- `documentation/docs/policies/monitoring/workers-anomaly-detection-zscore.md` — statistical alerting
- `documentation/docs/policies/monitoring/on-call-rotation-pagerduty.md` — incident escalation
- `documentation/docs/policies/monitoring/synthetic-monitoring-playwright.md` — deep synthetic checks

## Sources

- Cloudflare Workers Scheduled Handlers — https://developers.cloudflare.com/workers/runtime-apis/handlers/scheduled/
- D1 Batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Atom Syndication Format — RFC 4287
- SQLite Window Functions — https://www.sqlite.org/windowfunctions.html
