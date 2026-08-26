# Cloudflare Network Error Logging for Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

End users report intermittent connection failures to a Cloudflare Workers-fronted application that are invisible in the Worker's own error logs. The Workers Tail API only captures events that reach the isolate; TCP-level failures, TLS handshake timeouts, and Cloudflare edge connectivity errors never enter the Worker's execution context. Without Network Error Logging (NEL), these browser-side connectivity failures are a blind spot in the observability stack.

## Context

Network Error Logging (NEL) is a W3C specification (RFC 9218) that instructs browsers to collect and report low-level network failures — DNS lookup errors, TCP connection timeouts, TLS negotiation failures, and HTTP protocol errors — to a configured reporting endpoint. Cloudflare natively integrates NEL headers into edge responses; when the Worker response includes `NEL` and `Report-To` headers, Cloudflare's edge automatically injects the reporting endpoint infrastructure at its PoPs and batches browser-side network failure reports to the specified collector. This makes NEL uniquely effective for Workers because even failures that never reach the isolate (e.g., edge-to-browser TLS errors, Cloudflare itself returning a 52x error before invoking the Worker) are captured and forwarded to the collector endpoint. A separate lightweight Worker acts as the NEL report collector, stores events in D1 for trending, and alerts on error rate spikes.

## Configuring NEL Headers from a Worker

Inject `NEL` and `Report-To` response headers from the Worker to activate browser-side failure collection.

```typescript
// src/nel-middleware.ts
export interface NELConfig {
  reportingGroup: string;
  reportToEndpoint: string;
  maxAgeSeconds?: number;
  includeSubdomains?: boolean;
  successFraction?: number;
  failureFraction?: number;
}

export function applyNELHeaders(
  response: Response,
  config: NELConfig
): Response {
  const {
    reportingGroup = "nel-collector",
    reportToEndpoint,
    maxAgeSeconds = 86400,
    includeSubdomains = false,
    successFraction = 0.0,  // Only report failures; reporting successes adds noise
    failureFraction = 1.0,
  } = config;

  const reportTo = JSON.stringify({
    group: reportingGroup,
    max_age: maxAgeSeconds,
    endpoints: [{ url: reportToEndpoint }],
    include_subdomains: includeSubdomains,
  });

  const nel = JSON.stringify({
    report_to: reportingGroup,
    max_age: maxAgeSeconds,
    include_subdomains: includeSubdomains,
    success_fraction: successFraction,
    failure_fraction: failureFraction,
  });

  const headers = new Headers(response.headers);
  headers.set("Report-To", reportTo);
  headers.set("NEL", nel);

  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

// src/index.ts
import { applyNELHeaders } from "./nel-middleware";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const response = await handleRequest(request, env);

    return applyNELHeaders(response, {
      reportingGroup: "nel-collector",
      reportToEndpoint: "https://nel-collector.my-team.workers.dev/report",
      maxAgeSeconds: 86400,
      failureFraction: 1.0,
      successFraction: 0.01, // 1% success sample for baseline
    });
  },
} satisfies ExportedHandler<Env>;
```

## NEL Report Collector Worker

A dedicated Worker receives NEL reports (POSTed as `application/reports+json`) from browsers, validates them, and persists events to D1 for querying.

```typescript
// workers/nel-collector/src/index.ts
export interface Env {
  DB: D1Database;
}

// W3C NEL report schema (subset)
interface NELReport {
  type: "network-error";
  age: number;
  url: string;
  user_agent: string;
  body: {
    elapsed_time: number;
    method: string;
    phase: "connection" | "dns" | "request" | "response" | "application";
    protocol: string;
    referrer: string;
    sampling_fraction: number;
    server_ip: string;
    status_code: number;
    type:
      | "ok"
      | "tcp.timed_out"
      | "tcp.reset"
      | "tcp.refused"
      | "dns.name_not_resolved"
      | "dns.failed"
      | "tls.cert.date_invalid"
      | "tls.cert.authority_invalid"
      | "tls.cert.invalid"
      | "http.error"
      | "abandoned"
      | "unknown";
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const contentType = request.headers.get("Content-Type") ?? "";
    if (!contentType.includes("application/reports+json")) {
      return new Response("Unsupported Media Type", { status: 415 });
    }

    let reports: NELReport[];
    try {
      reports = await request.json();
    } catch {
      return new Response("Bad Request", { status: 400 });
    }

    const nelReports = reports.filter((r) => r.type === "network-error");

    if (nelReports.length > 0) {
      const stmt = env.DB.prepare(`
        INSERT INTO nel_events
          (reported_at, url, error_type, phase, protocol, elapsed_ms, status_code, server_ip, user_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `);

      await env.DB.batch(
        nelReports.map((r) =>
          stmt.bind(
            new Date().toISOString(),
            r.url,
            r.body.type,
            r.body.phase,
            r.body.protocol,
            r.body.elapsed_time,
            r.body.status_code,
            r.body.server_ip,
            r.user_agent
          )
        )
      );
    }

    // 204 is the expected response for report collectors
    return new Response(null, { status: 204 });
  },
} satisfies ExportedHandler<Env>;
```

## D1 Schema and Error Trend Queries

```sql
-- migrations/001_nel_schema.sql
CREATE TABLE IF NOT EXISTS nel_events (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  reported_at  TEXT NOT NULL,
  url          TEXT NOT NULL,
  error_type   TEXT NOT NULL,
  phase        TEXT NOT NULL,
  protocol     TEXT NOT NULL,
  elapsed_ms   INTEGER,
  status_code  INTEGER,
  server_ip    TEXT,
  user_agent   TEXT
);

CREATE INDEX IF NOT EXISTS idx_nel_type_ts
  ON nel_events (error_type, reported_at);

-- Top 10 error types over last 24 hours
SELECT
  error_type,
  phase,
  COUNT(*) AS occurrences,
  ROUND(AVG(elapsed_ms), 0) AS avg_elapsed_ms
FROM nel_events
WHERE reported_at >= datetime('now', '-24 hours')
  AND error_type != 'ok'
GROUP BY error_type, phase
ORDER BY occurrences DESC
LIMIT 10;

-- TCP timeout rate over time (5-minute buckets)
SELECT
  strftime('%Y-%m-%dT%H:%M', reported_at, 'unixepoch',
    '-' || (CAST(strftime('%M', reported_at) AS INTEGER) % 5) || ' minutes') AS bucket,
  COUNT(*) AS total,
  SUM(CASE WHEN error_type = 'tcp.timed_out' THEN 1 ELSE 0 END) AS tcp_timeouts,
  ROUND(SUM(CASE WHEN error_type = 'tcp.timed_out' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS timeout_rate_pct
FROM nel_events
WHERE reported_at >= datetime('now', '-6 hours')
GROUP BY bucket
ORDER BY bucket DESC;
```

## Anti-patterns

- Setting `failure_fraction: 0` — this disables NEL collection entirely; the field must be > 0.0 to collect any failure reports.
- Sending NEL reports to the same Worker origin being monitored — if that Worker is down, the browser cannot deliver failure reports; always use a separate, independent Worker or a third-party reporting endpoint.
- Storing raw user-agent strings without hashing PII — NEL reports contain partial URL and IP information that may be subject to GDPR Article 4(1); hash or truncate before persistence.
- Using a `max_age` shorter than your deployment cycle — browsers cache NEL policy for `max_age` seconds; a 60-second `max_age` causes every page load to re-negotiate the policy, flooding the Report-To endpoint.

## Gotchas

- NEL reports are delivered asynchronously by the browser, often minutes or hours after the network failure occurred; the `age` field in the report body (in milliseconds since the failure) must be used to reconstruct the true error timestamp.
- Some browsers (notably Firefox) implement NEL but cap the number of queued reports; under high error conditions, reports may be dropped at the browser level before delivery.
- Cloudflare's own edge errors (52x, origin unreachable) do NOT appear in the Worker Tail API; they appear only in NEL reports and in Cloudflare's native Logpush `http_requests` dataset as `edge_response_status`.
- The `Report-To` header is deprecated in favour of the `Reporting-Endpoints` header in the Reporting API Level 1; deploy both headers in parallel during the transition period to maintain coverage across browser versions.

## Verification

```bash
# Confirm NEL headers are present on Worker responses
curl -si https://my-worker.example.com/ \
  | grep -E "^(NEL|Report-To):"

# Query collector D1 for recent errors
wrangler d1 execute nel-db \
  --command "SELECT error_type, COUNT(*) FROM nel_events WHERE reported_at >= datetime('now', '-1 hour') GROUP BY error_type ORDER BY 2 DESC;"

# Simulate a report delivery to the collector
curl -s -X POST https://nel-collector.my-team.workers.dev/report \
  -H "Content-Type: application/reports+json" \
  -d '[{"type":"network-error","age":100,"url":"https://my-worker.example.com/","user_agent":"test","body":{"elapsed_time":500,"method":"GET","phase":"connection","protocol":"h2","referrer":"","sampling_fraction":1.0,"server_ip":"104.18.0.1","status_code":0,"type":"tcp.timed_out"}}]' \
  -w "\nHTTP %{http_code}\n"
```

## Related

- `infra/workers-opentelemetry-tail-workers.md`
- `infra/cloudflare-workers-limits-resource-planning.md`
- `infra/monitoring-sla-slo-sli.md`
- `infra/alerting-fatigue-reduction.md`

## Sources

- https://developers.cloudflare.com/network-error-logging/
- https://www.w3.org/TR/network-error-logging/
- https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/NEL
