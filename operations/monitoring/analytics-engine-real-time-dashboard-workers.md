# Analytics Engine Real-Time Dashboard Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your team wants a live operations dashboard showing request rates, error counts, p95 latency, and top paths — updated every few seconds — without standing up Grafana, a Prometheus remote-write endpoint, or any external observability infrastructure. The data is already in Analytics Engine. You want a self-contained Worker that both queries Analytics Engine and serves the dashboard HTML with Server-Sent Events (SSE) for real-time updates, deployable in under five minutes with a single `wrangler deploy`.

## Context

Cloudflare Analytics Engine exposes a SQL API over HTTPS. A Worker can query it on a timer or per-request, then stream the results to the browser via SSE. Because Workers can handle both the static HTML serve and the SSE stream from a single script, the entire dashboard is one Worker: no separate frontend deploy, no external data source, no database. The data latency is ~60 seconds (Analytics Engine ingestion lag) which is acceptable for operational dashboards but not for sub-minute alerting.

**Architecture:**
- `GET /` — serves the dashboard HTML (inline)
- `GET /stream` — SSE endpoint; polls Analytics Engine every 10 seconds and sends JSON events
- `GET /snapshot` — returns the latest metrics as JSON for programmatic consumers

---

## 1. Analytics Engine Queries Used by the Dashboard

```typescript
// dashboard-worker/src/queries.ts

export const QUERIES = {
  requestRate: `
    SELECT
      toStartOfMinute(timestamp) AS minute,
      COUNT()                    AS requests,
      COUNTIf(double1 >= 500)    AS errors
    FROM WORKER_METRICS
    WHERE timestamp > NOW() - INTERVAL '15' MINUTE
    GROUP BY minute
    ORDER BY minute ASC
  `,

  p95Latency: `
    SELECT
      quantilesTDigest(0.5, 0.95, 0.99)(double2) AS latency_quantiles
    FROM WORKER_METRICS
    WHERE timestamp > NOW() - INTERVAL '5' MINUTE
  `,

  topPaths: `
    SELECT
      blob2                 AS path,
      COUNT()               AS hits,
      COUNTIf(double1 >= 500) AS errors,
      AVG(double2)          AS avg_latency_ms
    FROM WORKER_METRICS
    WHERE timestamp > NOW() - INTERVAL '5' MINUTE
    GROUP BY path
    ORDER BY hits DESC
    LIMIT 10
  `,

  errorsByCountry: `
    SELECT
      blob3   AS country,
      COUNT() AS errors
    FROM WORKER_METRICS
    WHERE double1 >= 500
      AND timestamp > NOW() - INTERVAL '5' MINUTE
    GROUP BY country
    ORDER BY errors DESC
    LIMIT 10
  `,
};
```

---

## 2. Analytics Engine Query Helper

```typescript
// dashboard-worker/src/ae.ts

export interface Env {
  CF_ACCOUNT_ID: string;
  AE_TOKEN: string;
  AE_DATASET: string;  // e.g. "WORKER_METRICS"
}

export async function queryAE<T = Record<string, unknown>>(
  env: Pick<Env, "CF_ACCOUNT_ID" | "AE_TOKEN">,
  sql: string,
): Promise<T[]> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.AE_TOKEN}`,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: sql,
      signal: AbortSignal.timeout(8_000),
    },
  );

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`AE SQL error ${res.status}: ${text}`);
  }

  const json = await res.json() as { data: T[] };
  return json.data ?? [];
}

export async function fetchDashboardSnapshot(env: Env): Promise<{
  requestRate: unknown[];
  topPaths: unknown[];
  errorsByCountry: unknown[];
  p95Latency: unknown[];
  queriedAt: string;
}> {
  const { QUERIES } = await import("./queries.js");
  const [requestRate, p95Latency, topPaths, errorsByCountry] = await Promise.all([
    queryAE(env, QUERIES.requestRate),
    queryAE(env, QUERIES.p95Latency),
    queryAE(env, QUERIES.topPaths),
    queryAE(env, QUERIES.errorsByCountry),
  ]);

  return { requestRate, p95Latency, topPaths, errorsByCountry, queriedAt: new Date().toISOString() };
}
```

---

## 3. SSE Stream Endpoint

```typescript
// dashboard-worker/src/sse.ts

import type { Env } from "./ae.js";
import { fetchDashboardSnapshot } from "./ae.js";

const POLL_INTERVAL_MS = 10_000;

export async function handleSseStream(env: Env): Promise<Response> {
  const { readable, writable } = new TransformStream<string, string>();
  const writer = writable.getWriter();
  const encoder = new TextEncoder();

  const write = (event: string, data: unknown): void => {
    const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
    writer.write(encoder.encode(payload)).catch(() => {});
  };

  // Background poll loop — runs until the client disconnects
  (async () => {
    while (true) {
      try {
        const snapshot = await fetchDashboardSnapshot(env);
        write("snapshot", snapshot);
      } catch (err) {
        write("error", { message: String(err) });
      }

      await new Promise<void>((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
  })().catch(() => writer.close());

  return new Response(readable as unknown as ReadableStream<Uint8Array>, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
      "Access-Control-Allow-Origin": "*",
    },
  });
}
```

---

## 4. Main Worker — Route Handler and Inline Dashboard HTML

```typescript
// dashboard-worker/src/index.ts

import type { Env } from "./ae.js";
import { fetchDashboardSnapshot } from "./ae.js";
import { handleSseStream } from "./sse.js";
import { DASHBOARD_HTML } from "./html.js";

export type { Env };

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/stream") {
      return handleSseStream(env);
    }

    if (url.pathname === "/snapshot") {
      try {
        const data = await fetchDashboardSnapshot(env);
        return Response.json(data, { headers: { "Cache-Control": "no-store" } });
      } catch (err) {
        return Response.json({ error: String(err) }, { status: 502 });
      }
    }

    // Default: serve dashboard HTML
    return new Response(DASHBOARD_HTML, {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-cache",
      },
    });
  },
};
```

---

## 5. Inline Dashboard HTML Client (SSE Consumer)

```typescript
// dashboard-worker/src/html.ts
// Inline HTML served at GET / — connects to the /stream SSE endpoint

export const DASHBOARD_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Workers Ops Dashboard</title>
  <style>
    :root { --bg: #0f1117; --fg: #e2e8f0; --accent: #38bdf8; --err: #f87171; --card: #1e2432; }
    body { margin: 0; background: var(--bg); color: var(--fg); font: 14px/1.5 'JetBrains Mono', monospace; }
    h1   { padding: 1rem 1.5rem; margin: 0; font-size: 1rem; letter-spacing: .05em; color: var(--accent); border-bottom: 1px solid #2a3040; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; padding: 1rem 1.5rem; }
    .card { background: var(--card); border-radius: 6px; padding: 1rem; }
    .card h2 { margin: 0 0 .5rem; font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; color: #64748b; }
    table { width: 100%; border-collapse: collapse; font-size: .85rem; }
    td, th { padding: .25rem .5rem; text-align: right; }
    th { text-align: left; color: #64748b; font-weight: normal; }
    td:first-child { text-align: left; }
    .status { padding: .25rem 1.5rem; font-size: .75rem; color: #64748b; }
    .ok  { color: #4ade80; }
    .err { color: var(--err); }
  </style>
</head>
<body>
  <h1>Workers Ops Dashboard</h1>
  <div class="grid">
    <div class="card"><h2>Top Paths (5 min)</h2><div id="paths">loading…</div></div>
    <div class="card"><h2>Errors by Country (5 min)</h2><div id="countries">loading…</div></div>
    <div class="card"><h2>Requests / Errors (15 min)</h2><div id="rate">loading…</div></div>
  </div>
  <div class="status" id="status">connecting…</div>
  <script>
    const sse = new EventSource('/stream');
    const status = document.getElementById('status');

    sse.addEventListener('snapshot', (e) => {
      const d = JSON.parse(e.data);
      status.textContent = 'Last updated: ' + d.queriedAt;

      // Top paths table
      const pathRows = (d.topPaths || []).map(r =>
        \`<tr><td>\${r.path}</td><td>\${r.hits}</td><td class="err">\${r.errors}</td><td>\${(+r.avg_latency_ms).toFixed(0)} ms</td></tr>\`
      ).join('');
      document.getElementById('paths').innerHTML =
        '<table><tr><th>Path</th><th>Hits</th><th>Errs</th><th>Avg</th></tr>' + pathRows + '</table>';

      // Errors by country table
      const countryRows = (d.errorsByCountry || []).map(r =>
        \`<tr><td>\${r.country}</td><td class="err">\${r.errors}</td></tr>\`
      ).join('');
      document.getElementById('countries').innerHTML =
        '<table><tr><th>Country</th><th>Errors</th></tr>' + countryRows + '</table>';

      // Request rate mini-table (last 5 rows)
      const rateRows = (d.requestRate || []).slice(-5).map(r =>
        \`<tr><td>\${r.minute?.replace('T',' ').slice(0,16)}</td><td>\${r.requests}</td><td class="err">\${r.errors}</td></tr>\`
      ).join('');
      document.getElementById('rate').innerHTML =
        '<table><tr><th>Minute</th><th>Reqs</th><th>Errs</th></tr>' + rateRows + '</table>';
    });

    sse.addEventListener('error', () => {
      status.textContent = 'Stream error — reconnecting…';
    });
  </script>
</body>
</html>`;
```

---

## Anti-patterns

- **Running Analytics Engine queries on every incoming browser request** — one browser tab opening the dashboard should not fire four AE SQL queries; SSE decouples the query cadence from the client count by running the poll loop once in the Worker, not per-client.
- **Setting `Cache-Control: max-age` on the SSE stream** — SSE responses must not be cached; always send `Cache-Control: no-cache` and `Connection: keep-alive`.
- **Querying AE with windows narrower than 60 seconds** — data is not available in AE until ~60 s after ingestion; a `INTERVAL '30' SECOND` window will consistently return empty results.
- **Embedding the AE token in the dashboard HTML** — the dashboard HTML is served to browsers; the AE API token must remain server-side in the Worker's environment variables, never in the client script.

## Gotchas

- Workers have a **30-second CPU time limit** per invocation. An SSE stream that holds open a long-lived connection may be killed after 30 seconds of wall time; structure the Worker to reset the connection after a reasonable interval and let the browser EventSource reconnect automatically.
- `TransformStream` in Workers is synchronous on the write side; if the poll loop falls behind (AE query takes >10 s), the browser may receive stale data. Add a timeout via `AbortSignal.timeout`.
- Free tier Workers do not support long-lived streaming responses; this pattern requires the **Workers Paid plan**.
- Multiple browser tabs each opening `/stream` create independent SSE connections, each running their own poll loop. For dashboards with many concurrent viewers, fan-out via a Durable Object is preferable to avoid multiplied AE query load.

## Verification

```bash
# 1. Set secrets
wrangler secret put AE_TOKEN
wrangler secret put CF_ACCOUNT_ID

# 2. Deploy
wrangler deploy

# 3. Open dashboard in browser
open https://dashboard.example.workers.dev/

# 4. Verify SSE stream directly
curl -N https://dashboard.example.workers.dev/stream

# 5. Verify snapshot endpoint returns structured JSON
curl -s https://dashboard.example.workers.dev/snapshot | jq .queriedAt

# 6. Confirm data updates every ~10 s by watching the "Last updated" field in the browser
```

## Related

- `cloudflare-analytics-engine-grafana-dashboard.md`
- `analytics-engine-multi-environment-comparison-dashboard.md`
- `analytics-engine-sql-api-programmatic-querying.md`
- `workers-tail-real-time-log-streaming.md`
- `analytics-engine-write-limits-and-backpressure.md`

## Sources

- Cloudflare Analytics Engine SQL API — developers.cloudflare.com/analytics/analytics-engine/sql-api
- Server-Sent Events — MDN Web Docs — developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
- Cloudflare Workers Streaming — developers.cloudflare.com/workers/runtime-apis/streams/transformstream
- Workers Limits — developers.cloudflare.com/workers/platform/limits
