# Capacity Planning Metrics for Durable Objects

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your Durable Objects-backed feature works fine in staging but approaches Cloudflare's per-object storage limits in production as user data accumulates. You receive a billing surprise from unexpected DO CPU time, or you discover that a hot DO receives thousands of concurrent WebSocket connections that queue behind its single-threaded execution model. You lack the instrumentation to forecast growth, detect hot spots, or right-size your object sharding strategy before users are affected.

## Context

Durable Objects have several hard limits that, when approached, degrade latency or cause errors rather than scaling elastically the way a Worker does:

| Limit | Value (as of 2025) |
|---|---|
| Storage per object | 10 GB (SQL) / 128 MB (KV) |
| Keys per object (KV) | No enforced limit, but performance degrades above ~1M keys |
| Rows per SQLite object | ~20M practical limit before scan performance suffers |
| WebSocket connections per object | No hard limit, but serialization means one at a time executes |
| Subrequest concurrency per request | 6 simultaneous `fetch()` calls |
| CPU time per request | 30 seconds (same as Workers) |

Because each DO is a single-threaded actor, concurrency does not help for sequential workloads — all requests to the same object are serialized. This means hot-spot detection is as important as storage capacity planning.

## Instrumenting Per-Object Storage Usage

Durable Objects provide a `storage.list()` method and a `storage.getAll()` method but no built-in "how much space am I using?" API. For SQLite-backed DOs, `sql.databaseSize` returns approximate bytes used.

```javascript
// storage-reporter/src/GameRoomDO.js
export class GameRoomDO {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === '/metrics') {
      return this.handleMetrics();
    }

    // ... normal business logic
  }

  async handleMetrics() {
    const metrics = {};

    // SQLite storage size (bytes) — available on SQL-backed DOs
    try {
      metrics.sqliteSizeBytes = this.state.storage.sql.databaseSize;
    } catch {
      metrics.sqliteSizeBytes = null; // KV-backed DO
    }

    // KV key count (approximate; enumerate only first 1000 for cheap estimate)
    const kvSample = await this.state.storage.list({ limit: 1000 });
    metrics.kvKeyCountSample = kvSample.size;
    metrics.kvKeyCountIsExact = kvSample.size < 1000;

    // Alarm state
    const alarmTime = await this.state.storage.getAlarm();
    metrics.hasAlarm = alarmTime !== null;
    metrics.alarmAt = alarmTime;

    // WebSocket connections (only meaningful if this DO manages connections)
    const sockets = this.state.getWebSockets();
    metrics.activeWebSockets = sockets.length;

    return new Response(JSON.stringify(metrics), {
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
```

## Capacity Sweep Worker: Sampling Across Objects

Individual DO metrics must be fetched object-by-object. A sweep Worker uses a known set of DO IDs (stored in KV or D1) to poll each one and write aggregate metrics to Analytics Engine.

```javascript
// capacity-sweep/src/index.js
export default {
  async scheduled(event, env) {
    // Retrieve the list of active DO IDs from D1
    const { results } = await env.DB.prepare(
      'SELECT do_id, room_id FROM active_rooms WHERE last_active > ?'
    ).bind(Date.now() - 86400_000).all();

    const tasks = results.map(({ do_id, room_id }) =>
      sweepObject(do_id, room_id, env)
    );

    // Fan out with concurrency limit to avoid rate limits
    const CONCURRENCY = 20;
    for (let i = 0; i < tasks.length; i += CONCURRENCY) {
      await Promise.allSettled(tasks.slice(i, i + CONCURRENCY));
    }
  },
};

async function sweepObject(doId, roomId, env) {
  const stub = env.GAME_ROOM.get(env.GAME_ROOM.idFromString(doId));

  let metrics;
  try {
    const resp = await stub.fetch('https://do-internal/metrics', {
      signal: AbortSignal.timeout(5000),
    });
    metrics = await resp.json();
  } catch (err) {
    console.error(`Sweep failed for ${doId}:`, err.message);
    return;
  }

  // Emit to Analytics Engine for time-series capacity tracking
  env.ANALYTICS.writeDataPoint({
    blobs: [doId, roomId],
    doubles: [
      metrics.sqliteSizeBytes ?? 0,
      metrics.kvKeyCountSample,
      metrics.activeWebSockets,
    ],
    indexes: [doId],
  });

  // Alert if approaching storage limit (e.g., 80% of 10 GB SQLite cap)
  const GB10 = 10 * 1024 * 1024 * 1024;
  if ((metrics.sqliteSizeBytes ?? 0) > GB10 * 0.8) {
    await sendCapacityAlert(doId, roomId, metrics, env);
  }
}
```

## Detecting Hot Objects via CPU Time Instrumentation

A "hot" object is one that receives a disproportionate share of requests, causing other requests to queue behind its serialized execution. Measure CPU time per request inside the DO and emit it as a metric.

```javascript
export class GameRoomDO {
  // Inside the fetch handler:
  async fetch(request) {
    const start = Date.now();

    try {
      const response = await this.handleRequest(request);
      const wallMs = Date.now() - start;

      this.env.ANALYTICS.writeDataPoint({
        blobs: [this.state.id.toString()],
        doubles: [wallMs, 1],
        indexes: [this.state.id.toString()],
      });

      return response;
    } catch (err) {
      this.env.ANALYTICS.writeDataPoint({
        blobs: [this.state.id.toString(), 'error'],
        doubles: [Date.now() - start, 1],
        indexes: [this.state.id.toString()],
      });
      throw err;
    }
  }
}
```

Query hot objects in Analytics Engine:

```sql
-- Top 20 hottest Durable Objects by P95 wall time in the last hour
SELECT
  blob1                                   AS object_id,
  COUNT()                                 AS request_count,
  SUM(double2)                            AS total_requests,
  quantileWeighted(0.95)(double1, double2) AS p95_wall_ms,
  quantileWeighted(0.50)(double1, double2) AS p50_wall_ms,
  MAX(double1)                            AS max_wall_ms
FROM do_request_metrics
WHERE timestamp > NOW() - INTERVAL '1' HOUR
GROUP BY object_id
ORDER BY p95_wall_ms DESC
LIMIT 20
```

Objects at the top of this list are candidates for sharding or redesign.

## Forecasting Storage Growth with Linear Regression

Once you have multiple days of `sqliteSizeBytes` data in Analytics Engine, you can forecast time-to-limit using a simple linear extrapolation.

```javascript
// forecast/src/index.js — a scheduled Worker that writes a forecast
export default {
  async scheduled(event, env) {
    // Query last 7 days of storage samples per object
    const query = `
      SELECT
        blob1 AS object_id,
        toUnixTimestamp(toStartOfHour(timestamp)) AS hour_ts,
        AVG(double1) AS avg_bytes
      FROM do_capacity_metrics
      WHERE timestamp > NOW() - INTERVAL '7' DAY
        AND double1 > 0
      GROUP BY object_id, hour_ts
      ORDER BY object_id, hour_ts
    `;

    const { data } = await queryAnalyticsEngine(query, env);

    // Group by object_id
    const byObject = {};
    for (const row of data) {
      if (!byObject[row.object_id]) byObject[row.object_id] = [];
      byObject[row.object_id].push({ ts: row.hour_ts, bytes: row.avg_bytes });
    }

    for (const [objectId, points] of Object.entries(byObject)) {
      if (points.length < 24) continue; // Need at least 24 hours of data

      const slope = linearRegressionSlope(points);
      const latestBytes = points[points.length - 1].bytes;
      const limitBytes = 10 * 1024 ** 3; // 10 GB

      const remainingBytes = limitBytes - latestBytes;
      const hoursToLimit = remainingBytes / slope; // slope is bytes/hour
      const daysToLimit = hoursToLimit / 24;

      if (daysToLimit < 30) {
        await sendCapacityForecastAlert(objectId, daysToLimit, latestBytes, env);
      }
    }
  },
};

function linearRegressionSlope(points) {
  const n = points.length;
  const meanX = points.reduce((s, p) => s + p.ts, 0) / n;
  const meanY = points.reduce((s, p) => s + p.bytes, 0) / n;
  const num = points.reduce((s, p) => s + (p.ts - meanX) * (p.bytes - meanY), 0);
  const den = points.reduce((s, p) => s + (p.ts - meanX) ** 2, 0);
  return den === 0 ? 0 : num / den; // bytes per second; multiply by 3600 for per-hour
}
```

## Sharding Strategy Triggers

Use capacity metrics to decide when to shard an object:

| Metric | Threshold | Action |
|---|---|---|
| `sqliteSizeBytes` | > 8 GB (80% of 10 GB limit) | Plan migration to sharded namespace |
| `p95_wall_ms` | > 500 ms | Profile hot DO, consider sharding by user/region |
| `activeWebSockets` | > 1,000 | Add a connection-level coordinator DO |
| `daysToLimit` forecast | < 30 days | Begin sharding migration sprint |
| `kvKeyCountSample` | Exactly 1,000 (capped) | Switch to SQLite, evaluate actual key count |

## Anti-patterns

- **Using a single DO as a global lock or singleton** — a single `config` DO that every Worker hits on every request becomes a bottleneck immediately. Cache the DO's output in Workers KV or in the Worker's in-memory module state with a short TTL.
- **Not setting a sweep concurrency limit** — if you have 10,000 active objects and fire all 10,000 stub fetches at once, you will hit Workers subrequest limits (6 concurrent per Worker invocation is not a limit, but thousands of concurrent active connections to DOs can saturate account-level limits). Use a concurrency-limited loop.
- **Assuming `storage.list()` count equals used storage** — key count and storage bytes are independent. A single key with a 1 MB value uses more storage than 1,000 small keys. Measure both.
- **Conflating wall time with CPU time** — wall time includes storage I/O await, which does not count against the 30-second CPU limit. Use wall time as a latency signal and a proxy for contention; do not treat it as a CPU burn metric.

## Gotchas

- **`databaseSize` is approximate** — SQLite's `PRAGMA page_count * page_size` (which is what Cloudflare exposes) can diverge from the actual on-disk size by up to 20% after large deletions. Run `VACUUM` (supported in DO SQLite via `this.state.storage.sql.exec('VACUUM')`) to reclaim space and get an accurate post-vacuum size.
- **Sweep Worker must use `idFromString`, not `idFromName`** — if your production code creates DOs with `idFromName`, you must store the name (not the resulting ID string) in D1 and use `idFromName` in the sweep. The two methods produce different IDs; using `idFromString` with a name-derived ID returns a nonexistent object.
- **DOs in jurisdictions cannot be swept from another region** — if you use jurisdiction-restricted DOs (`idFromName(name, { jurisdiction: 'eu' })`), the sweep Worker must run in the same jurisdiction. Adjust `wrangler.toml` accordingly.

## Verification

1. Write a script that creates 10 test DOs, fills each with 1 MB of data, and confirms `sqliteSizeBytes` increases accordingly.
2. Run the sweep Worker manually with `wrangler dev --cron` and confirm Analytics Engine receives data points for each test object.
3. Simulate near-capacity by lowering the alert threshold to 10% of actual capacity and confirm the alert fires.
4. Query the capacity forecast for a test object growing at a known rate and verify the `daysToLimit` estimate is within 20% of expected.

## Related

- `cloudflare-analytics-engine.md` — writing and querying custom metrics
- `capacity-planning-metrics.md` — general capacity planning methodology
- `durable-objects` architecture patterns (see CLAUDE.md)
- `cost-monitoring-dashboards.md` — monitoring DO billing usage

## Sources

- Cloudflare Durable Objects limits: https://developers.cloudflare.com/durable-objects/platform/limits/
- Durable Objects storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- Durable Objects SQLite storage: https://developers.cloudflare.com/durable-objects/api/sql-storage/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
