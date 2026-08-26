# Cloudflare Tunnel Latency and Health Monitoring

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Tunnel (cloudflared) connects an on-premise or private-cloud origin to the
Cloudflare network. Users start seeing intermittent 502/503 responses or elevated latency.
The Cloudflare dashboard shows tunnel status as "healthy" because at least one connection
is alive, but individual connections are degraded, and your origin is overloaded on the
one remaining active connection. You need per-connection latency percentiles, reconnection
rate, and origin reachability tracked over time to detect partial degradation early.

## Context

Cloudflare Tunnel exposes metrics via a Prometheus-compatible `/metrics` endpoint that
`cloudflared` serves locally (default: `http://localhost:2000/metrics`). From inside a
private network, a lightweight scraper Worker deployed in the private network or a side-car
container ships these metrics to Analytics Engine via the Cloudflare Analytics Engine HTTP
API. Alternatively, Cloudflare Notifications can alert on tunnel state changes, but these
are coarse (up/down). Fine-grained latency and error rate require the Prometheus scrape path.

---

## 1. cloudflared Prometheus Metrics Reference

```bash
# Key metrics exposed by cloudflared /metrics
# tunnel_total_requests          counter  - total requests proxied
# tunnel_request_errors          counter  - requests that resulted in a proxy error
# tunnel_response_by_code        counter  - breakdown by HTTP status class
# tunnel_connections             gauge    - active tunnel connections per edge PoP
# tunnel_ha_connections          gauge    - number of HA tunnel connections
# tunnel_reconnects              counter  - reconnection attempts
# cloudflared_build_info         gauge    - version info
# coredns_dns_request_duration_seconds  histogram  - internal DNS latency

# Start cloudflared with metrics enabled:
# cloudflared tunnel run --metrics localhost:2000 <TUNNEL_NAME>
```

## 2. Metrics Scraper Worker (Runs in Private Network via Cloudflare Service Token)

```typescript
// scraper/index.ts — scheduled every 30 seconds via cron "* * * * *" (1-minute min cadence)
export interface Env {
  CLOUDFLARED_METRICS_URL: string; // e.g. "http://localhost:2000/metrics"
  ANALYTICS: AnalyticsEngineDataset;
  TUNNEL_ID: string;
}

interface ParsedMetrics {
  totalRequests: number;
  requestErrors: number;
  activeConnections: number;
  reconnects: number;
  status2xx: number;
  status5xx: number;
}

function parsePrometheusLine(text: string, metricName: string): number {
  const lines = text.split('\n');
  for (const line of lines) {
    if (line.startsWith(metricName) && !line.startsWith('#')) {
      const parts = line.split(' ');
      const val = parseFloat(parts[parts.length - 1]);
      return isNaN(val) ? 0 : val;
    }
  }
  return 0;
}

function parseMetrics(body: string): ParsedMetrics {
  return {
    totalRequests:    parsePrometheusLine(body, 'tunnel_total_requests'),
    requestErrors:    parsePrometheusLine(body, 'tunnel_request_errors'),
    activeConnections: parsePrometheusLine(body, 'tunnel_ha_connections'),
    reconnects:       parsePrometheusLine(body, 'tunnel_reconnects'),
    status2xx:        parsePrometheusLine(body, 'tunnel_response_by_code{status_code="2xx"}'),
    status5xx:        parsePrometheusLine(body, 'tunnel_response_by_code{status_code="5xx"}'),
  };
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const res = await fetch(env.CLOUDFLARED_METRICS_URL, {
      signal: AbortSignal.timeout(8000),
    });

    if (!res.ok) {
      console.error(`[tunnel-scraper] metrics fetch failed: ${res.status}`);
      env.ANALYTICS.writeDataPoint({
        blobs: [env.TUNNEL_ID, 'scrape_failed'],
        doubles: [0, 0, 0, res.status],
        indexes: [env.TUNNEL_ID],
      });
      return;
    }

    const body = await res.text();
    const m = parseMetrics(body);
    const errorRate = m.totalRequests > 0 ? m.requestErrors / m.totalRequests : 0;

    env.ANALYTICS.writeDataPoint({
      blobs: [env.TUNNEL_ID, m.activeConnections >= 2 ? 'ha_ok' : 'degraded'],
      doubles: [
        m.activeConnections,  // double1: HA connection count
        m.reconnects,         // double2: cumulative reconnect counter
        errorRate,            // double3: error rate
        m.status5xx,          // double4: 5xx response count
      ],
      indexes: [env.TUNNEL_ID],
    });

    if (m.activeConnections < 2) {
      console.warn(`[tunnel-scraper] tunnel=${env.TUNNEL_ID} ha_connections=${m.activeConnections} (below HA minimum)`);
    }
  },
};
```

## 3. Synthetic Origin Reachability Probe

```typescript
// probe/index.ts — scheduled every minute, probes origin through the tunnel
export interface Env {
  ORIGIN_HEALTH_URL: string; // e.g. internal service health endpoint
  ANALYTICS: AnalyticsEngineDataset;
  TUNNEL_ID: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const start = performance.now();
    let statusCode = 0;
    let reachable = false;

    try {
      const res = await fetch(env.ORIGIN_HEALTH_URL, {
        method: 'GET',
        signal: AbortSignal.timeout(10_000),
        headers: { 'User-Agent': 'tunnel-health-probe/1.0' },
      });
      statusCode = res.status;
      reachable = res.ok;
      await res.body?.cancel(); // drain without buffering
    } catch (err) {
      statusCode = 0;
      console.warn(`[probe] origin unreachable: ${err}`);
    }

    const latencyMs = performance.now() - start;

    env.ANALYTICS.writeDataPoint({
      blobs: [env.TUNNEL_ID, reachable ? 'reachable' : 'unreachable', String(statusCode)],
      doubles: [latencyMs, reachable ? 0 : 1],
      indexes: [env.TUNNEL_ID],
    });
  },
};
```

## 4. Analytics Engine SQL — Tunnel Health Dashboard Queries

```sql
-- HA connection count trend (last 1 hour, 5-minute buckets)
SELECT
  toStartOfFiveMinutes(timestamp)        AS bucket,
  blob1                                  AS tunnel_id,
  MIN(double1)                           AS min_ha_connections,
  AVG(double1)                           AS avg_ha_connections
FROM tunnel_metrics
WHERE timestamp >= NOW() - INTERVAL '1' HOUR
GROUP BY bucket, tunnel_id
ORDER BY bucket DESC

-- Origin probe latency and availability (last 30 minutes)
SELECT
  blob1                                            AS tunnel_id,
  SUM(_sample_interval * double2)                  AS unreachable_count,
  SUM(_sample_interval)                            AS probe_count,
  SUM(_sample_interval * double2) / SUM(_sample_interval) AS unavailability_rate,
  quantileWeighted(0.50)(double1, _sample_interval) AS p50_latency_ms,
  quantileWeighted(0.99)(double1, _sample_interval) AS p99_latency_ms
FROM tunnel_probe_metrics
WHERE timestamp >= NOW() - INTERVAL '30' MINUTE
GROUP BY blob1
```

## 5. Alerting Worker — HA Degradation and High Error Rate

```typescript
// monitor/tunnel-alert.ts — cron every 5 minutes
export interface Env {
  ANALYTICS_API_TOKEN: string;
  CF_ACCOUNT_ID: string;
  SLACK_WEBHOOK: string;
  PAGERDUTY_KEY: string;
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const query = `
      SELECT
        blob1                                              AS tunnel_id,
        MIN(double1)                                       AS min_ha_connections,
        AVG(double3)                                       AS avg_error_rate
      FROM tunnel_metrics
      WHERE timestamp >= NOW() - INTERVAL '5' MINUTE
      GROUP BY tunnel_id
    `;

    const res = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
      {
        method: 'POST',
        headers: { Authorization: `Bearer ${env.ANALYTICS_API_TOKEN}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      }
    );
    const { data } = (await res.json()) as {
      data: Array<{ tunnel_id: string; min_ha_connections: number; avg_error_rate: number }>;
    };

    for (const row of data) {
      const severity = row.min_ha_connections < 1 ? 'critical' : 'warning';

      if (row.min_ha_connections < 2 || row.avg_error_rate > 0.05) {
        await fetch(env.SLACK_WEBHOOK, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: `[tunnel-alert] *${row.tunnel_id}* — ha_connections=${row.min_ha_connections} error_rate=${(row.avg_error_rate * 100).toFixed(1)}% (${severity})`,
          }),
        });
      }
    }
  },
};
```

## 6. Cloudflare Notification Webhook for Tunnel State Changes

```typescript
// notifications/tunnel-state-webhook.ts — receives Cloudflare Tunnel status change events
// Configure at: Cloudflare Dashboard → Notifications → Tunnel Health Alert
export default {
  async fetch(request: Request, env: { ANALYTICS: AnalyticsEngineDataset }): Promise<Response> {
    if (request.method !== 'POST') return new Response('method not allowed', { status: 405 });

    const payload = await request.json() as {
      data: { tunnel_id: string; tunnel_name: string; tunnel_status: string };
      timestamp: string;
    };

    const { tunnel_id, tunnel_name, tunnel_status } = payload.data;

    env.ANALYTICS.writeDataPoint({
      blobs: [tunnel_id, tunnel_name, tunnel_status],
      doubles: [tunnel_status === 'down' ? 1 : 0],
      indexes: [tunnel_id],
    });

    console.log(`[tunnel-event] tunnel=${tunnel_name} id=${tunnel_id} status=${tunnel_status}`);
    return new Response('ok');
  },
};
```

---

## Anti-patterns

- **Relying solely on the Cloudflare Notifications "Tunnel Health Alert"**: this alerts only
  on full tunnel down (all connections lost). Partial HA degradation (4 → 1 connection) is
  invisible until the last connection drops.
- **Scraping `/metrics` on a cadence faster than 30 seconds**: cloudflared updates internal
  counters every ~10 seconds; faster scraping wastes subrequests without adding resolution.
- **Checking origin reachability through the public Cloudflare hostname**: this tests the
  full path (DNS + CDN + tunnel + origin). Test the tunnel by hitting the tunnel-internal
  URL directly so you isolate tunnel health from Cloudflare edge health.
- **Not monitoring `tunnel_reconnects` rate**: a rising reconnect counter without an outright
  down event signals an unstable network path between cloudflared and Cloudflare edge PoPs.

## Gotchas

- `cloudflared` metrics labels include `connection_id` and `location` (PoP code); parsing
  the full label set from Prometheus text format requires a proper line parser, not a simple
  `startsWith`. The above example uses exact label strings — adapt if cloudflared's label
  order changes between versions.
- The local `/metrics` endpoint is HTTP (not HTTPS) by default. If scraping from a Worker
  inside the private network, ensure the `CLOUDFLARED_METRICS_URL` is reachable and that
  the Worker has a Service Binding or private network route to the cloudflared host.
- `tunnel_ha_connections` reports the count across *all* edge PoPs connected. A tunnel with
  4 PoP connections that drops to 1 still shows as "healthy" in the dashboard but is
  effectively routing all traffic through a single edge connection.
- Analytics Engine `writeDataPoint` is async and fire-and-forget; if the scraper Worker
  itself times out (e.g., the metrics endpoint is slow), the data point is not written and
  the gap looks like a healthy gap rather than a scrape failure. Emit a sentinel blob on
  scrape failure (shown in example above).

## Verification

```bash
# Check live cloudflared metrics locally
curl -s http://localhost:2000/metrics | grep -E '^tunnel_|^cloudflared_build'

# Query Analytics Engine for tunnel availability
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query":"SELECT blob1, MIN(double1) AS min_ha, AVG(double3) AS avg_err_rate FROM tunnel_metrics WHERE timestamp >= NOW() - INTERVAL '\''15'\'' MINUTE GROUP BY blob1"}'

# Verify probe reachability data
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/analytics_engine/sql" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query":"SELECT count(), SUM(double2) AS unreachable FROM tunnel_probe_metrics WHERE timestamp >= NOW() - INTERVAL '\''30'\'' MINUTE"}'
```

## Related

- `cloudflare-health-checks-origin-monitoring.md`
- `synthetic-monitoring-uptime-checks.md`
- `uptime-monitoring-workers-cron-synthetic.md`
- `dns-resolution-monitoring.md`
- `workers-slo-burn-rate-cloudflare-notifications.md`

## Sources

- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/monitor-tunnels/
- https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/deploy-tunnels/deployment-guides/
- https://developers.cloudflare.com/notifications/notification-types/#tunnel-health-alert
- https://developers.cloudflare.com/analytics/analytics-engine/
- https://github.com/cloudflare/cloudflared — /metrics endpoint documentation
