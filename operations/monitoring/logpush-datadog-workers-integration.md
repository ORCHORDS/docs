# Logpush to Datadog Integration for Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Your observability stack is centered on Datadog but Workers logs are siloed in
Cloudflare's dashboard or in a separate R2 bucket. Engineers correlating a Workers
error with an upstream API failure must context-switch between two UIs. You want
Workers HTTP request logs, Tail Worker structured logs, and Cloudflare Access/WAF
events to flow into Datadog so they can be correlated with APM traces, Live
Tail-searched, and used to trigger Datadog Monitors.

---

## Context

Cloudflare Logpush supports HTTP endpoints as a destination. Datadog's Log Intake
API (`https://http-intake.logs.datadoghq.com/api/v2/logs`) accepts newline-delimited
JSON (NDJSON) or a JSON array with gzip encoding. Logpush sends batched NDJSON by
default, making the integration straightforward without a transform layer.

The two main data sources you will push:

1. **Workers HTTP requests** — one log line per request, fields include URL, status,
   duration, worker script name, Ray ID.
2. **Workers Tail events** — structured console.log / console.error lines plus
   outcome metadata, pushed via a Tail Worker that formats and forwards to Datadog.

---

## 1. Create a Logpush Job via API

```bash
# Create a Logpush job targeting Datadog HTTP intake
# Replace DD_API_KEY, DD_SITE, and ZONE_ID with your values
# DD_SITE: datadoghq.com (US1), datadoghq.eu (EU), us3.datadoghq.com, etc.

curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/logpush/jobs" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "workers-to-datadog",
    "destination_conf": "https://http-intake.logs.datadoghq.com/api/v2/logs?ddsource=cloudflare&ddtags=env:production,service:workers&header_DD-API-KEY=$DD_API_KEY",
    "dataset": "workers",
    "logpull_options": "fields=ClientRequestURI,ClientRequestMethod,EdgeResponseStatus,WorkerScriptName,EdgeStartTimestamp,WorkerStatus,WorkerCPUTime,EdgeRequestHost,RayID,ClientCountry,ClientIP&timestamps=rfc3339",
    "enabled": true,
    "frequency": "high"
  }'
```

The `header_DD-API-KEY=` segment in `destination_conf` injects the API key as an
HTTP header. Cloudflare substitutes the environment variable value from the
account's configured secrets at delivery time.

---

## 2. Tail Worker — Forward Structured Logs to Datadog

For console-level log lines (not captured by Logpush), use a Tail Worker:

```typescript
// src/tail-to-datadog.ts
import type { TailEventMessage } from "@cloudflare/workers-types";

interface Env {
  DD_API_KEY: string;
  DD_SITE: string; // e.g. "datadoghq.com"
  DD_SERVICE: string;
  DD_ENV: string;
}

interface DatadogLogEntry {
  message: string;
  level: string;
  timestamp: string;
  ddsource: string;
  ddtags: string;
  service: string;
  worker_script: string;
  ray_id?: string;
  outcome: string;
  cpu_time_ms?: number;
}

export default {
  async tail(events: TailEventMessage[], env: Env): Promise<void> {
    const entries: DatadogLogEntry[] = [];

    for (const event of events) {
      const base: Omit<DatadogLogEntry, "message" | "level"> = {
        timestamp: new Date(event.eventTimestamp ?? Date.now()).toISOString(),
        ddsource: "cloudflare-workers",
        ddtags: `env:${env.DD_ENV},worker:${event.scriptName ?? "unknown"}`,
        service: env.DD_SERVICE,
        worker_script: event.scriptName ?? "unknown",
        outcome: event.outcome ?? "unknown",
        cpu_time_ms: (event as TailEventMessage & { cpuTime?: number }).cpuTime,
      };

      // Write one entry per log line emitted by the Worker
      if (event.logs && event.logs.length > 0) {
        for (const log of event.logs) {
          entries.push({
            ...base,
            level: log.level,
            message: log.message.map(String).join(" "),
          });
        }
      }

      // Write one entry per exception
      for (const exc of event.exceptions ?? []) {
        entries.push({
          ...base,
          level: "error",
          message: `${exc.name}: ${exc.message}`,
        });
      }

      // If no logs/exceptions, emit a synthetic access log entry
      if ((!event.logs || event.logs.length === 0) && (!event.exceptions || event.exceptions.length === 0)) {
        const req = event.event?.request;
        entries.push({
          ...base,
          level: event.outcome === "ok" ? "info" : "error",
          message: req
            ? `${req.method} ${req.url} → ${event.response?.status ?? "?"}`
            : `Worker invocation ${event.outcome}`,
        });
      }
    }

    if (entries.length === 0) return;

    // Datadog accepts JSON array payload up to 5MB
    const payload = JSON.stringify(entries);
    await fetch(`https://http-intake.logs.${env.DD_SITE}/api/v2/logs`, {
      method: "POST",
      headers: {
        "DD-API-KEY": env.DD_API_KEY,
        "Content-Type": "application/json",
      },
      body: payload,
    });
  },
};
```

---

## 3. Datadog Log Pipeline — Remap Cloudflare Fields

Create a Datadog Log Processing Pipeline to remap Logpush field names to
Datadog's standard attribute taxonomy:

```json
{
  "name": "Cloudflare Workers Logpush",
  "filter": { "query": "source:cloudflare" },
  "processors": [
    {
      "type": "date-remapper",
      "sources": ["EdgeStartTimestamp"],
      "name": "Remap timestamp"
    },
    {
      "type": "status-remapper",
      "sources": ["EdgeResponseStatus"],
      "name": "Remap HTTP status"
    },
    {
      "type": "attribute-remapper",
      "sources": ["WorkerScriptName"],
      "target": "service",
      "name": "Map script name to service"
    },
    {
      "type": "attribute-remapper",
      "sources": ["RayID"],
      "target": "trace_id",
      "name": "Map Ray ID to trace_id for correlation"
    },
    {
      "type": "url-parser",
      "sources": ["ClientRequestURI"],
      "name": "Parse request URL"
    }
  ]
}
```

Apply this via Terraform (`datadog_logs_custom_pipeline`) or the Datadog UI under
Logs → Configuration → Pipelines.

---

## 4. Datadog Monitor — Workers Error Rate

```bash
# Create a Datadog Monitor for Workers 5xx error rate via API
curl -X POST "https://api.datadoghq.com/api/v1/monitor" \
  -H "DD-API-KEY: $DD_API_KEY" \
  -H "DD-APPLICATION-KEY: $DD_APP_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Cloudflare Workers 5xx Error Rate",
    "type": "log alert",
    "query": "logs(\"source:cloudflare EdgeResponseStatus:>=500\").index(\"*\").rollup(\"count\").by(\"WorkerScriptName\").last(\"5m\") > 50",
    "message": "Workers {{WorkerScriptName.name}} has {{value}} 5xx errors in last 5m.\n\n@pagerduty-workers-oncall",
    "tags": ["service:workers", "env:production"],
    "options": {
      "thresholds": { "critical": 50, "warning": 20 },
      "notify_no_data": false,
      "evaluation_delay": 60
    }
  }'
```

---

## 5. Verify Logpush Delivery Health

```bash
# Check Logpush job status and last delivery time
curl "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/logpush/jobs" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {name, enabled, last_complete, last_error}'

# Send a test batch to validate Datadog is receiving
curl -X POST \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/logpush/validate/destination/exists" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"destination_conf\": \"https://http-intake.logs.datadoghq.com/api/v2/logs?ddsource=cloudflare&header_DD-API-KEY=$DD_API_KEY\"}"
```

---

## Anti-patterns

- **Pushing all Logpush fields to Datadog** — Datadog pricing scales with ingested
  log volume. Use `logpull_options` to select only the fields you query. Dropping
  unused fields like `ClientASN`, `WAFRuleID`, and `OriginIP` can reduce volume
  by 40–60%.
- **Sending Tail Worker logs AND HTTP request Logpush for the same Worker** — this
  duplicates access log data. Use Logpush for HTTP metadata and Tail Worker only
  for console-level structured logs and exceptions.
- **Storing the Datadog API key in `destination_conf` as plaintext in Terraform
  state** — use the `$ENV_VAR` substitution syntax in `destination_conf` so the
  key is stored as a Cloudflare account secret, not in the job config.
- **Not setting `ddsource=cloudflare`** — without this tag, Datadog's out-of-the-box
  Cloudflare integration dashboard and grok parsers will not activate.

---

## Gotchas

- Logpush batches logs with up to **5 minutes of delay** on the `low` frequency
  setting. Use `"frequency": "high"` for near-real-time delivery (< 1 minute lag);
  it increases Cloudflare's outbound HTTPS call frequency but not your cost.
- Datadog's Log Intake API has a **5 MB per payload** limit and **1000 entries per
  batch**. Logpush honors neither limit — it can send batches up to 10,000 entries.
  Add a Worker proxy between Logpush and Datadog if you hit `413 Payload Too Large`
  responses.
- Cloudflare sets `Content-Type: application/x-ndjson` on Logpush HTTP deliveries.
  Datadog accepts both NDJSON and JSON array from this endpoint, but validate with
  a curl test before relying on it in production.
- Logpush to HTTP destinations does **not retry on 429 or 5xx**. If Datadog is
  unavailable, those log batches are lost. For critical audit logs, push to R2
  as a durable backup and forward to Datadog with a separate Lambda or Worker.

---

## Verification

```bash
# In Datadog Live Tail, run this filter to confirm logs are arriving:
# source:cloudflare @WorkerScriptName:my-production-worker

# Confirm field mapping worked:
# @service should equal WorkerScriptName value
# @timestamp should be EdgeStartTimestamp parsed as RFC3339

# Check Logpush job for delivery errors:
curl "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/logpush/jobs/$JOB_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result | {last_complete, last_error, failed_records}'
```

---

## Related

- `cloudflare-logpush-setup.md`
- `workers-logpush-observability-pipeline.md`
- `datadog-log-management.md`
- `datadog-apm-setup.md`
- `logpush-filter-expressions-cost-control.md`
- `workers-tail-real-time-log-streaming.md`

---

## Sources

- https://developers.cloudflare.com/logs/get-started/enable-destinations/http/
- https://developers.cloudflare.com/logs/reference/log-fields/zone/workers-trace-events/
- https://docs.datadoghq.com/api/latest/logs/
- https://docs.datadoghq.com/logs/log_configuration/pipelines/
- https://docs.datadoghq.com/integrations/cloudflare/
