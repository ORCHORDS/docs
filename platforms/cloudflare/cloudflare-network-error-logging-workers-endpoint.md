# Cloudflare Network Error Logging Workers Endpoint

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Users report intermittent failures loading your site — blank screens, partial
loads, DNS errors — but your server logs show no corresponding errors because
the requests never reached your origin.  You need to capture browser-side
network failures (TCP resets, TLS handshake errors, DNS failures, HTTP/2 GOAWAY
frames) before they vanish.  The W3C **Network Error Logging (NEL)** API
combined with a Cloudflare Worker as the reporting endpoint gives you a
persistent, analysable record of client-side network anomalies.

---

## Context

**Network Error Logging (NEL)** is a W3C specification implemented in Chrome
and Edge (not Safari or Firefox) that allows origins to instruct browsers to
collect and report network-level errors.  Two response headers configure it:

- `NEL` — JSON policy telling the browser what to collect, how long to retain
  the policy, and which reporting group to use.
- `Report-To` — defines the reporting endpoint group(s) where the browser sends
  NEL reports.

Reports are sent as `POST` requests with `Content-Type: application/reports+json`
(or the legacy `application/report` for older Chrome versions).  Each report
describes a single network failure event.

A Cloudflare Worker is an ideal NEL collector because:
- It is globally available with no cold start overhead for reporting traffic.
- It can fan out to Logpush, Workers Analytics Engine, or R2 without any
  additional infrastructure.
- The same Worker can serve both your application and handle `/.well-known/nel`
  reports.

Key NEL report fields:

| Field | Description |
|---|---|
| `type` | `"network-error"` |
| `url` | The URL that failed |
| `body.type` | Error type: `dns.name_not_resolved`, `tcp.connection_refused`, `tls.certificate.validity_failed`, `http.protocol.error`, etc. |
| `body.phase` | `connection`, `dns`, `request`, `response` |
| `body.status_code` | HTTP status if request reached the server |
| `body.elapsed_time` | Time from request start to failure (ms) |
| `body.referrer` | Page referrer |
| `age` | Seconds since the error occurred |

---

## Worker: NEL Collector Endpoint

```typescript
// src/index.ts
export interface Env {
  NEL_BUCKET: R2Bucket;           // optional — archive raw reports
  ANALYTICS: AnalyticsEngineDataset; // optional — real-time metrics
}

interface NelReportBody {
  type: string;
  url: string;
  referrer: string;
  status_code: number;
  protocol: string;
  method: string;
  request_headers: Record<string, string>;
  response_headers: Record<string, string>;
  phase: "dns" | "connection" | "request" | "response" | "application";
  elapsed_time: number;
}

interface NelReport {
  age: number;
  type: "network-error";
  url: string;
  user_agent: string;
  body: NelReportBody;
}

/** Add NEL + Report-To headers to any response. */
export function injectNelHeaders(response: Response, reportingOrigin: string): Response {
  const headers = new Headers(response.headers);

  // Report-To group that the browser POSTs to
  const reportTo = JSON.stringify({
    group: "nel-collector",
    max_age: 86400,
    endpoints: [{ url: `${reportingOrigin}/nel-report` }],
    include_subdomains: true,
  });

  // NEL policy: collect all errors, 1% sample of successes
  const nel = JSON.stringify({
    report_to: "nel-collector",
    max_age: 86400,
    include_subdomains: true,
    failure_fraction: 1.0,
    success_fraction: 0.01,
  });

  headers.set("Report-To", reportTo);
  headers.set("NEL", nel);

  return new Response(response.body, { status: response.status, headers });
}

async function handleNelReport(
  request: Request,
  env: Env,
  ctx: ExecutionContext,
): Promise<Response> {
  // Accept both application/reports+json and application/report
  const ct = request.headers.get("content-type") ?? "";
  if (!ct.includes("application/reports") && !ct.includes("application/report")) {
    return new Response("Unsupported Media Type", { status: 415 });
  }

  let reports: NelReport[];
  try {
    reports = (await request.json()) as NelReport[];
    // Older Chrome may send a single object rather than an array
    if (!Array.isArray(reports)) reports = [reports as unknown as NelReport];
  } catch {
    return new Response("Bad Request", { status: 400 });
  }

  ctx.waitUntil(
    (async () => {
      const ts = Date.now();
      const ip = request.headers.get("cf-connecting-ip") ?? "unknown";
      const country = request.headers.get("cf-ipcountry") ?? "XX";

      for (const report of reports) {
        if (report.type !== "network-error") continue;

        // Structured log for Tail Workers / Logpush
        console.log(
          JSON.stringify({
            event: "nel_report",
            ts,
            ip,
            country,
            age: report.age,
            failedUrl: report.url,
            userAgent: report.user_agent,
            errorType: report.body.type,
            phase: report.body.phase,
            protocol: report.body.protocol,
            method: report.body.method,
            statusCode: report.body.status_code,
            elapsedMs: report.body.elapsed_time,
            referrer: report.body.referrer,
          }),
        );

        // Emit to Workers Analytics Engine for dashboards
        if (env.ANALYTICS) {
          env.ANALYTICS.writeDataPoint({
            blobs: [
              report.body.type,
              report.body.phase,
              report.body.protocol ?? "unknown",
              country,
            ],
            doubles: [report.body.elapsed_time ?? 0, 1],
            indexes: [new URL(report.url).hostname],
          });
        }
      }

      // Archive raw batch to R2 for compliance/replay
      if (env.NEL_BUCKET && reports.length > 0) {
        const key = `nel/${new Date(ts).toISOString().slice(0, 10)}/${ts}-${crypto.randomUUID()}.json`;
        await env.NEL_BUCKET.put(key, JSON.stringify(reports), {
          httpMetadata: { contentType: "application/json" },
        });
      }
    })(),
  );

  // Return 204 — browsers expect a 2xx; body is ignored
  return new Response(null, { status: 204 });
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/nel-report" && request.method === "POST") {
      return handleNelReport(request, env, ctx);
    }

    // For all other requests, inject NEL headers into the upstream response
    const response = await fetch(request);
    return injectNelHeaders(response, `https://${url.hostname}`);
  },
};
```

---

## `wrangler.toml` Configuration

```toml
name        = "nel-collector"
main        = "src/index.ts"
compatibility_date = "2025-01-01"

[[r2_buckets]]
binding  = "NEL_BUCKET"
bucket_name = "nel-reports"

[[analytics_engine_datasets]]
binding = "ANALYTICS"
dataset = "nel_events"
```

---

## Querying NEL Data in Analytics Engine

```bash
# Top error types over the last 24 hours
curl -sS "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT blob1 AS error_type, SUM(_sample_interval) AS count FROM nel_events WHERE timestamp > now() - INTERVAL '\''24'\'' HOUR GROUP BY error_type ORDER BY count DESC LIMIT 20"
  }' | jq .
```

```bash
# NEL errors by country
curl -sS "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/analytics_engine/sql" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "SELECT blob4 AS country, blob1 AS error_type, SUM(_sample_interval) AS count FROM nel_events WHERE timestamp > now() - INTERVAL '\''1'\'' HOUR GROUP BY country, error_type ORDER BY count DESC LIMIT 50"
  }' | jq .
```

---

## CORS Configuration for Cross-Origin Reporting

If your reporting endpoint is on a different origin (e.g. a dedicated
`reports.example.com` Worker), browsers send a preflight.  Handle it:

```typescript
function handleCorsPreflight(request: Request): Response | null {
  if (request.method !== "OPTIONS") return null;
  const origin = request.headers.get("origin");
  // Only accept from your own domains
  const allowed = ["https://example.com", "https://app.example.com"];
  if (!origin || !allowed.includes(origin)) {
    return new Response(null, { status: 403 });
  }
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "POST",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
    },
  });
}
```

---

## Anti-patterns

- **Setting `failure_fraction: 1.0` on very high-traffic sites** — every client
  that experiences a network error will report it immediately.  On high-traffic
  origins this can overwhelm the reporting endpoint.  Use `failure_fraction: 0.1`
  to sample 10% of errors during rollout.
- **Pointing `Report-To` at a third-party domain** — browsers will only send
  reports to same-site or explicitly allowed reporting origins.  Use a subdomain
  of your own apex domain to avoid CORS complexity.
- **Forgetting `include_subdomains: true`** — without this, subdomains must set
  their own NEL headers.  One top-level policy with `include_subdomains` covers
  the full domain tree.
- **Expecting NEL from Safari/Firefox** — NEL is a Chromium-only feature.  It
  supplements rather than replaces server-side error tracking.
- **Logging raw IPs to long-term storage** — NEL reports include the client IP
  via `cf-connecting-ip`.  Scrub or hash it before writing to R2 if you are
  subject to GDPR/CCPA.

---

## Gotchas

- The `Report-To` header must be returned on the **same origin** as the failing
  resource.  If the Worker serves `example.com` but the report collector lives
  at `reports.example.com`, set `Report-To` on `example.com` responses and add
  CORS on the reports endpoint.
- Browsers cache NEL policies for `max_age` seconds.  Changing the reporting
  endpoint requires waiting for the existing `max_age` to expire on all clients,
  or re-deploying with `max_age: 0` to clear it.
- Chrome batches NEL reports and sends them opportunistically — typically within
  a few minutes but potentially hours later if the browser is offline.  The
  `age` field in the report body tells you when the error originally occurred.
- The `success_fraction` counter generates a report for **every successful
  request** at that sample rate.  Even `0.01` on a high-traffic site can
  generate millions of success reports per day; keep it at `0.001` or lower, or
  set it to `0` if you only care about failures.
- NEL reports do not include the full request/response body or query string in
  the `url` field — the URL is stripped of credentials and fragments but query
  parameters are preserved.  Scrub sensitive query parameters before logging.

---

## Verification

```bash
# Check that NEL headers are present on your origin
curl -sI https://example.com/ | grep -E "^(NEL|Report-To):"

# Expected output (formatted for readability):
# NEL: {"report_to":"nel-collector","max_age":86400,"include_subdomains":true,"failure_fraction":1.0,"success_fraction":0.01}
# Report-To: {"group":"nel-collector","max_age":86400,"endpoints":[{"url":"https://example.com/nel-report"}],"include_subdomains":true}

# Simulate a NEL report POST to your Worker (test payload)
curl -sS -X POST https://example.com/nel-report \
  -H "Content-Type: application/reports+json" \
  -d '[{
    "age": 42,
    "type": "network-error",
    "url": "https://example.com/api/data",
    "user_agent": "Mozilla/5.0",
    "body": {
      "type": "tcp.connection_refused",
      "url": "https://example.com/api/data",
      "referrer": "https://example.com/",
      "status_code": 0,
      "protocol": "h2",
      "method": "GET",
      "phase": "connection",
      "elapsed_time": 150
    }
  }]'
# Expected: HTTP 204 No Content
```

---

## Related

- `workers-analytics-engine.md` — Workers Analytics Engine as the metrics
  backend for NEL error rates and trends
- `workers-tail-workers.md` — Tail Worker reading `console.log` emitted by the
  NEL collector for real-time alerting
- `cloudflare-logpush-custom-fields-workers-dataset.md` — shipping console.log
  NEL events via Logpush to S3/R2/SIEM
- `r2-best-practices.md` — R2 storage for archiving raw NEL report batches
- `csp-headers-and-cf-waf.md` — companion W3C reporting APIs: CSP reporting
  via `report-uri` and `report-to`

---

## Sources

- W3C Network Error Logging specification:
  https://www.w3.org/TR/network-error-logging/
- Chrome NEL implementation status:
  https://chromestatus.com/feature/5391249376804864
- Reporting API (Report-To):
  https://www.w3.org/TR/reporting/
- Workers Analytics Engine reference:
  https://developers.cloudflare.com/analytics/analytics-engine/
- Cloudflare R2 binding:
  https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
