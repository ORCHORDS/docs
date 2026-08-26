# Workers Request Size Anomaly Detection D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Workers API endpoint that normally receives payloads under 10 KB suddenly starts receiving requests in the 2–5 MB range. The Worker stays within CPU limits but D1 insert latency spikes and the request bodies exhaust the `request.body` read buffer faster than expected. You need to detect abnormally large inbound requests in real time, record them for audit, and alert before a single malformed or malicious request degrades downstream D1 performance for all concurrent users.

## Context

Cloudflare Workers enforce a **100 MB request body limit** for paid plans, but most application-level payloads should be measured in kilobytes. Anomalously large requests can signal:

- A misconfigured client sending uncompressed blobs instead of references
- A content-injection or payload-stuffing attack probing for injection surface
- A legitimate bulk-upload routed to the wrong endpoint
- A serialisation bug producing runaway JSON (circular-reference omitted, array not chunked)

The detection pattern combines three layers: (1) measure the `Content-Length` header and, when absent, stream-measure the body before processing; (2) log a structured anomaly record including source IP, country, and path; (3) persist anomaly records to D1 for trend analysis and attach an Analytics Engine write for real-time alerting.

---

## 1. Measuring Request Size Without Fully Buffering

When `Content-Length` is present, use it. When absent, stream the body through a `TransformStream` to tally bytes without keeping the entire payload in memory.

```typescript
// worker/src/request-size.ts

export interface RequestSizeMeasurement {
  contentLengthHeader: number | null;
  measuredBytes: number | null;
  method: string;
  path: string;
  clampedAt: number | null; // non-null if we stopped reading early
}

const MAX_MEASURE_BYTES = 10 * 1024 * 1024; // 10 MB ceiling — stop counting if exceeded

export async function measureRequestSize(
  request: Request,
  passThrough: boolean,
): Promise<{ measurement: RequestSizeMeasurement; body: ReadableStream | null }> {
  const clHeader = request.headers.get("Content-Length");
  const contentLengthHeader = clHeader ? parseInt(clHeader, 10) : null;

  if (!request.body) {
    return {
      measurement: {
        contentLengthHeader,
        measuredBytes: 0,
        method: request.method,
        path: new URL(request.url).pathname,
        clampedAt: null,
      },
      body: null,
    };
  }

  // If Content-Length is present and we don't need to re-stream, skip measurement
  if (contentLengthHeader !== null && !passThrough) {
    return {
      measurement: {
        contentLengthHeader,
        measuredBytes: contentLengthHeader,
        method: request.method,
        path: new URL(request.url).pathname,
        clampedAt: null,
      },
      body: request.body,
    };
  }

  let measuredBytes = 0;
  let clampedAt: number | null = null;
  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      measuredBytes += chunk.byteLength;
      if (measuredBytes > MAX_MEASURE_BYTES) {
        clampedAt = MAX_MEASURE_BYTES;
      }
      controller.enqueue(chunk);
    },
  });

  // Pipe the original body through the counter; the downstream handler reads `readable`
  request.body.pipeTo(writable);

  return {
    measurement: {
      contentLengthHeader,
      measuredBytes,   // will be populated as `readable` is consumed
      method: request.method,
      path: new URL(request.url).pathname,
      clampedAt,
    },
    body: readable,
  };
}
```

---

## 2. Main Worker — Detect, Log, and Persist Anomalies

```typescript
// worker/src/index.ts

import type { D1Database, AnalyticsEngineDataset } from "@cloudflare/workers-types";
import { measureRequestSize } from "./request-size.js";

export interface Env {
  DB: D1Database;
  REQUEST_ANOMALIES: AnalyticsEngineDataset;
}

const ANOMALY_THRESHOLD_BYTES = 100 * 1024; // 100 KB — tune per endpoint

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const t0 = Date.now();

    // Only measure POST / PUT / PATCH
    if (!["POST", "PUT", "PATCH"].includes(request.method)) {
      return new Response("ok", { status: 200 });
    }

    const { measurement, body } = await measureRequestSize(request, true);

    // Reconstruct the request with the pass-through body stream
    const rehydrated = new Request(request, { body });

    // Read the actual body for processing (this completes the stream measurement)
    let parsed: unknown;
    try {
      parsed = await rehydrated.json();
    } catch {
      return new Response("bad request", { status: 400 });
    }

    const bodyBytes = measurement.measuredBytes ?? measurement.contentLengthHeader ?? 0;
    const isAnomaly = bodyBytes > ANOMALY_THRESHOLD_BYTES;

    const country = request.cf?.country ?? "unknown";
    const clientIp = request.headers.get("CF-Connecting-IP") ?? "unknown";

    if (isAnomaly) {
      console.log(JSON.stringify({
        event: "request.size.anomaly",
        path: url.pathname,
        method: request.method,
        bodyBytes,
        country,
        clientIp: clientIp.slice(0, 45), // truncate for log safety
        thresholdBytes: ANOMALY_THRESHOLD_BYTES,
        clampedAt: measurement.clampedAt,
      }));

      // Persist to D1 for trend queries (non-blocking)
      ctx.waitUntil(
        env.DB.prepare(
          `INSERT INTO request_size_anomalies
           (ts, path, method, body_bytes, country, client_ip_prefix, threshold_bytes)
           VALUES (?, ?, ?, ?, ?, ?, ?)`,
        )
          .bind(
            new Date().toISOString(),
            url.pathname,
            request.method,
            bodyBytes,
            country,
            clientIp.slice(0, 3) + "***",  // store only prefix
            ANOMALY_THRESHOLD_BYTES,
          )
          .run(),
      );

      // Write to Analytics Engine for real-time alerting
      env.REQUEST_ANOMALIES.writeDataPoint({
        blobs: [url.pathname, request.method, country],
        doubles: [bodyBytes, ANOMALY_THRESHOLD_BYTES, Date.now() - t0],
        indexes: [url.pathname],
      });
    }

    // Continue normal processing…
    return Response.json({ received: true, anomaly: isAnomaly });
  },
};
```

---

## 3. D1 Schema for Anomaly Persistence

```sql
-- migrations/0001_request_size_anomalies.sql
CREATE TABLE IF NOT EXISTS request_size_anomalies (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT    NOT NULL,          -- ISO-8601 timestamp
  path            TEXT    NOT NULL,
  method          TEXT    NOT NULL,
  body_bytes      INTEGER NOT NULL,
  country         TEXT    NOT NULL DEFAULT 'unknown',
  client_ip_prefix TEXT   NOT NULL DEFAULT '',
  threshold_bytes INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_anomalies_ts   ON request_size_anomalies (ts);
CREATE INDEX IF NOT EXISTS idx_anomalies_path ON request_size_anomalies (path, ts);
```

Apply with:

```bash
wrangler d1 execute MY_DB --remote --file=migrations/0001_request_size_anomalies.sql
```

---

## 4. Querying Anomaly Trends from D1

```typescript
// query-worker/src/index.ts — internal endpoint for ops tooling

export interface Env { DB: D1Database }

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const path = url.searchParams.get("path") ?? "%";
    const since = url.searchParams.get("since") ?? new Date(Date.now() - 3600_000).toISOString();

    // Top paths by anomaly count in the window
    const { results } = await env.DB.prepare(`
      SELECT
        path,
        method,
        country,
        COUNT(*)          AS anomaly_count,
        MAX(body_bytes)   AS max_body_bytes,
        AVG(body_bytes)   AS avg_body_bytes
      FROM request_size_anomalies
      WHERE ts >= ?
        AND path LIKE ?
      GROUP BY path, method, country
      ORDER BY anomaly_count DESC
      LIMIT 50
    `).bind(since, path).all();

    return Response.json(results);
  },
};
```

---

## 5. Analytics Engine Alert for Real-Time Spikes

```sql
-- Paths with > 10 anomalies in the last 5 minutes (run from a cron Worker)
SELECT
  blob1   AS path,
  blob2   AS method,
  blob3   AS country,
  COUNT() AS anomaly_count,
  MAX(double1) AS max_body_bytes
FROM REQUEST_ANOMALIES
WHERE timestamp > NOW() - INTERVAL '5' MINUTE
GROUP BY path, method, country
HAVING anomaly_count > 10
ORDER BY anomaly_count DESC;
```

```typescript
// alert-worker/src/index.ts

export interface Env {
  CF_ACCOUNT_ID: string;
  AE_TOKEN: string;
  SLACK_WEBHOOK_URL: string;
}

export default {
  async scheduled(_evt: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(checkAnomalySpike(env));
  },
};

async function checkAnomalySpike(env: Env): Promise<void> {
  const sql = `
    SELECT blob1 AS path, blob3 AS country, COUNT() AS n, MAX(double1) AS peak_bytes
    FROM REQUEST_ANOMALIES
    WHERE timestamp > NOW() - INTERVAL '5' MINUTE
    GROUP BY blob1, blob3
    HAVING n > 5
    ORDER BY n DESC
    LIMIT 5
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${env.AE_TOKEN}` },
      body: sql,
    },
  );

  const json = await res.json() as { data: Array<{ path: string; country: string; n: number; peak_bytes: number }> };
  if (!json.data?.length) return;

  const lines = json.data.map(
    (r) => `• \`${r.path}\` from ${r.country}: ${r.n} anomalies, peak ${(r.peak_bytes / 1024).toFixed(0)} KB`,
  );

  await fetch(env.SLACK_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: `:rotating_light: *Request size anomaly spike*\n${lines.join("\n")}` }),
  });
}
```

---

## Anti-patterns

- **Buffering the full body into memory just to measure it** — `await request.arrayBuffer()` consumes the stream; use a `TransformStream` to count bytes while keeping the stream available to the handler.
- **Blocking on D1 insert in the hot path** — anomaly persistence is audit data; always wrap in `ctx.waitUntil` to avoid adding latency to legitimate requests.
- **Using `Content-Length` as the only measure** — clients can send a false `Content-Length`; always stream-measure when accuracy matters.
- **Storing raw client IPs in D1** — even a partial IP is PII under GDPR; store only a prefix or a hashed value, and document the retention period.

## Gotchas

- `request.body` is a `ReadableStream` that can only be consumed once. Tee it (`request.body.tee()`) if both the measurement code and the handler need to read it; the `TransformStream` pattern above avoids tee by passing `readable` downstream.
- D1 has a **10 MB per-row limit** and a write throughput cap. If every request triggers a D1 insert, you will hit rate limits; gate inserts behind `isAnomaly`.
- Analytics Engine data has a **~60 second ingestion lag** before it appears in SQL queries; it is not suitable for sub-minute alerting windows — use a 5-minute minimum for cron-based alerts.
- `request.cf.country` is only populated on requests that pass through Cloudflare's edge routing; locally via `wrangler dev`, it is `undefined`.

## Verification

```bash
# 1. Deploy workers and apply D1 migration
wrangler d1 execute MY_DB --remote --file=migrations/0001_request_size_anomalies.sql
wrangler deploy

# 2. Send a normal-sized request — should produce no anomaly log
curl -s -X POST https://my-worker.example.workers.dev/api/data \
  -H "Content-Type: application/json" \
  -d '{"key":"value"}' | jq .anomaly

# 3. Send an oversized request
python3 -c "import json,sys; sys.stdout.write(json.dumps({'x':'a'*200000}))" | \
  curl -s -X POST https://my-worker.example.workers.dev/api/data \
  -H "Content-Type: application/json" --data-binary @- | jq .anomaly

# 4. Confirm anomaly=true in response and record in D1
wrangler d1 execute MY_DB --remote \
  --command "SELECT * FROM request_size_anomalies ORDER BY ts DESC LIMIT 5"

# 5. After ~90 s confirm Analytics Engine received the data point
```

## Related

- `workers-response-size-distribution.md`
- `workers-json-structured-logging-logpush-r2-retention.md`
- `tail-worker-exception-deduplication-fingerprinting-d1.md`
- `analytics-engine-write-limits-and-backpressure.md`
- `cloudflare-logpush-d1-log-aggregation.md`

## Sources

- Cloudflare Workers Request Body Limits — developers.cloudflare.com/workers/platform/limits#request-limits
- Streams API — MDN Web Docs — developer.mozilla.org/en-US/docs/Web/API/Streams_API
- Cloudflare D1 — developers.cloudflare.com/d1
- Cloudflare Analytics Engine — developers.cloudflare.com/analytics/analytics-engine
- GDPR and IP Address Storage — edpb.europa.eu/our-work-tools/our-documents/guidelines
