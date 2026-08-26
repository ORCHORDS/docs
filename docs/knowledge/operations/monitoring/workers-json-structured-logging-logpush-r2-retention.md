# Structured JSON Logging from Workers with Logpush to R2 for Long-Term Retention

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use Case

Your Cloudflare Workers emit logs via `console.log()`, but those logs are ephemeral—visible only in Wrangler tail sessions or a Tail Worker for a short window. For compliance, debugging, and long-term trend analysis you need logs persisted for 90+ days. You want logs in structured JSON (not bare strings), partitioned by date in R2 for cost-effective storage and queryable by tools like Athena, DuckDB, or Cloudflare's own Workers Analytics. You need to design the log schema up-front, configure a Logpush job for Workers Trace Events, and implement a log helper in TypeScript that ensures every log line is machine-parseable and includes all mandatory context fields.

---

## Context

Cloudflare **Logpush** can deliver Workers **Trace Events** (the same data that Tail Workers receive) directly to an R2 bucket in newline-delimited JSON format. Once in R2, the logs are queryable without maintaining a separate log aggregation server.

Key design decisions:

1. **Log schema**: What fields every log line must carry (correlation IDs, version, region, request context).
2. **Logpush job configuration**: Which fields to include, the output format, and the R2 prefix (partition) strategy.
3. **Log levels**: How to differentiate DEBUG/INFO/WARN/ERROR in structured form.
4. **Retention and lifecycle**: When to delete old logs (R2 object lifecycle rules).
5. **Query strategy**: How to read the logs from R2 using Workers or external tools.

This article covers the logging design and Logpush configuration. For the downstream Athena query layer, see `cloudflare-logpush-r2-partitioned-athena.md`.

---

## Log Schema Design

Every log line emitted by a Worker must include:

| Field | Type | Description |
|---|---|---|
| `timestamp` | ISO 8601 string | Event time |
| `level` | string | `DEBUG`, `INFO`, `WARN`, `ERROR` |
| `message` | string | Human-readable message |
| `service` | string | Worker name |
| `version` | string | Deploy version/git SHA |
| `ray` | string | Cloudflare Ray ID (request correlation) |
| `traceId` | string | W3C trace ID (if distributed tracing enabled) |
| `spanId` | string | W3C span ID |
| `method` | string | HTTP method |
| `path` | string | Normalised URL path |
| `status` | number | HTTP response status |
| `durationMs` | number | Wall clock request duration |
| `colo` | string | Cloudflare colo (e.g. "LHR") |
| `country` | string | Request origin country |
| `error` | object \| null | Error name, message, stack (only for WARN/ERROR) |
| `context` | object | Domain-specific key-value pairs |

---

## Structured Logger Implementation

```typescript
// src/logger.ts

export type LogLevel = "DEBUG" | "INFO" | "WARN" | "ERROR";

export interface LogContext {
  service: string;
  version: string;
  ray: string;
  traceId?: string;
  spanId?: string;
  method?: string;
  path?: string;
  colo?: string;
  country?: string;
}

export interface Logger {
  debug(message: string, context?: Record<string, unknown>): void;
  info(message: string, context?: Record<string, unknown>): void;
  warn(message: string, error?: Error, context?: Record<string, unknown>): void;
  error(message: string, error?: Error, context?: Record<string, unknown>): void;
  withContext(extra: Partial<LogContext>): Logger;
}

function serializeError(err: Error): Record<string, string> {
  return {
    name: err.name,
    message: err.message,
    stack: err.stack?.slice(0, 2000) ?? "", // truncate to avoid huge payloads
  };
}

export function createLogger(baseContext: LogContext): Logger {
  function emit(
    level: LogLevel,
    message: string,
    error?: Error,
    extra?: Record<string, unknown>
  ): void {
    // Workers runtime: console.log output is captured by Tail Workers and Logpush
    const entry: Record<string, unknown> = {
      timestamp: new Date().toISOString(),
      level,
      message,
      service: baseContext.service,
      version: baseContext.version,
      ray: baseContext.ray,
      ...(baseContext.traceId ? { traceId: baseContext.traceId } : {}),
      ...(baseContext.spanId ? { spanId: baseContext.spanId } : {}),
      ...(baseContext.method ? { method: baseContext.method } : {}),
      ...(baseContext.path ? { path: baseContext.path } : {}),
      ...(baseContext.colo ? { colo: baseContext.colo } : {}),
      ...(baseContext.country ? { country: baseContext.country } : {}),
      ...(error ? { error: serializeError(error) } : {}),
      ...(extra ? { context: extra } : {}),
    };

    // console.log is captured by Cloudflare as a structured log event
    // Do NOT use console.error/console.warn—they map to different log levels
    // in some runtimes; use a single output method for consistency
    console.log(JSON.stringify(entry));
  }

  return {
    debug(message, context) {
      emit("DEBUG", message, undefined, context);
    },
    info(message, context) {
      emit("INFO", message, undefined, context);
    },
    warn(message, error, context) {
      emit("WARN", message, error, context);
    },
    error(message, error, context) {
      emit("ERROR", message, error, context);
    },
    withContext(extra) {
      return createLogger({ ...baseContext, ...extra });
    },
  };
}
```

```typescript
// src/index.ts

import { createLogger } from "./logger";

interface Env {
  VERSION: string;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const ray = request.headers.get("cf-ray") ?? "unknown";
    const traceparent = request.headers.get("traceparent");
    const traceId = traceparent?.split("-")[1];
    const spanId = traceparent?.split("-")[2];

    const log = createLogger({
      service: "api-worker",
      version: env.VERSION,
      ray,
      traceId,
      spanId,
      method: request.method,
      path: url.pathname,
      colo: (request.cf as { colo?: string })?.colo,
      country: (request.cf as { country?: string })?.country ?? undefined,
    });

    const start = Date.now();
    log.info("Request received");

    try {
      const response = await handleRequest(request, env, log);
      const durationMs = Date.now() - start;

      log.info("Request completed", { status: response.status, durationMs });
      return response;
    } catch (err) {
      const durationMs = Date.now() - start;
      log.error("Request failed", err instanceof Error ? err : new Error(String(err)), {
        durationMs,
      });
      return new Response("Internal Server Error", { status: 500 });
    }
  },
};
```

---

## Configuring Logpush to R2

### Step 1: Create the R2 Bucket

```bash
wrangler r2 bucket create logs-long-term
```

### Step 2: Create a Logpush Job via the API

```bash
# Workers Trace Events Logpush job to R2
curl -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "workers-traces-to-r2",
    "logpull_options": "fields=Event,EventTimestampMs,Outcome,Exceptions,Logs,ScriptName",
    "destination_conf": "r2://logs-long-term/workers/{date}/?account-id='"${CF_ACCOUNT_ID}"'&access-key-id='"${R2_ACCESS_KEY_ID}"'&secret-access-key='"${R2_SECRET_ACCESS_KEY}"'",
    "dataset": "workers_trace_events",
    "enabled": true,
    "output_options": {
      "field_delimiter": "\n",
      "record_delimiter": "\n",
      "sample_rate": 1,
      "timestamp_format": "rfc3339",
      "batch_prefix": "",
      "batch_suffix": ""
    }
  }'
```

**R2 path template:** `workers/{date}/` causes Logpush to create daily partitions (e.g., `workers/2026-08-22/`). For higher-frequency querying, use `workers/{date}/{hour}/` for hourly partitions.

### Step 3: Verify the Logpush Job

```bash
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | select(.name == "workers-traces-to-r2")'
```

---

## R2 Partition Strategy

```
logs-long-term/
  workers/
    2026-08-20/
      20260820T000000Z--20260820T010000Z.log.gz
      20260820T010000Z--20260820T020000Z.log.gz
      ...
    2026-08-21/
      ...
    2026-08-22/
      ...
```

Logpush delivers files approximately every 5 minutes or when a file size threshold is reached (~5 MB), whichever comes first. Each file is gzip-compressed newline-delimited JSON.

For compliance queries spanning multiple days, list by prefix:

```typescript
// src/log-reader.ts (query Worker)

export async function listLogFiles(
  r2: R2Bucket,
  datePrefix: string // e.g. "workers/2026-08-22"
): Promise<string[]> {
  const listed = await r2.list({ prefix: datePrefix, limit: 1000 });
  return listed.objects.map((o) => o.key);
}

export async function streamLogLines(
  r2: R2Bucket,
  key: string,
  filter?: (line: Record<string, unknown>) => boolean
): Promise<Record<string, unknown>[]> {
  const obj = await r2.get(key);
  if (!obj) return [];

  // R2 returns gzip-compressed content; Workers can decompress with DecompressionStream
  const decompressed = obj.body.pipeThrough(new DecompressionStream("gzip"));
  const text = await new Response(decompressed).text();

  const results: Record<string, unknown>[] = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    try {
      const parsed = JSON.parse(line) as Record<string, unknown>;
      if (!filter || filter(parsed)) {
        results.push(parsed);
      }
    } catch {
      // Skip malformed lines
    }
  }
  return results;
}
```

---

## R2 Object Lifecycle for Retention

R2 supports object lifecycle rules to auto-delete objects older than a configured number of days:

```bash
# Set lifecycle rule: delete objects older than 90 days
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/r2/buckets/logs-long-term/lifecycle" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "id": "delete-logs-after-90-days",
        "filter": { "prefix": "workers/" },
        "expiration": { "days": 90 },
        "status": "enabled"
      }
    ]
  }'
```

For compliance requirements (e.g., SOC 2, GDPR), you may want two buckets:
- `logs-hot` — 30-day retention, low latency (queryable by ops team)
- `logs-cold` — 365-day retention, compliance archive

Logpush writes to one bucket; a nightly cron Worker copies files older than 30 days to the cold archive.

---

## Log Redaction Before Storage

Logpush captures everything emitted by `console.log()`. Ensure PII is stripped at the Worker level before it is logged:

```typescript
// src/redact.ts

const PII_PATTERNS: Array<[RegExp, string]> = [
  [/\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b/gi, "[EMAIL]"],
  [/\b(?:\d[ -]?){13,16}\b/g, "[CARD]"],      // credit card numbers
  [/\b\d{3}-\d{2}-\d{4}\b/g, "[SSN]"],         // US SSN
  [/"password"\s*:\s*"[^"]*"/gi, '"password":"[REDACTED]"'],
  [/"token"\s*:\s*"[^"]*"/gi, '"token":"[REDACTED]"'],
  [/"authorization"\s*:\s*"[^"]*"/gi, '"authorization":"[REDACTED]"'],
];

export function redact(value: string): string {
  let result = value;
  for (const [pattern, replacement] of PII_PATTERNS) {
    result = result.replace(pattern, replacement);
  }
  return result;
}

export function redactObject(obj: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(redact(JSON.stringify(obj)));
}
```

---

## Anti-Patterns

**Logging raw request/response bodies.** Even in debug mode, bodies may contain PII or credentials. Log body size and content-type, not the body itself.

**Using `console.error()` for structured logs.** Some Cloudflare environments surface `console.error` differently from `console.log`. Use `console.log(JSON.stringify(...))` for all structured log output.

**Emitting logs as formatted strings (`console.log("Request: " + url)`).** Logpush captures the raw string, which cannot be parsed downstream. Always use `JSON.stringify` on the full log entry.

**Skipping the `ray` field.** Without the `cf-ray` header, you cannot correlate a log line with a specific Cloudflare request or with Tail Worker events for the same request.

**Using `{date}/{hour}/{minute}` partitions for low-traffic services.** This creates thousands of tiny objects in R2, which are inefficient to list and query. Match partition granularity to your traffic volume.

---

## Gotchas

- **Logpush delivers Workers Trace Events, not raw `console.log()` output directly.** The `Logs` field in a Trace Event is an array of log entries including `Message` (the string passed to `console.log()`). If you pass a JSON string to `console.log()`, it appears as a string inside `Logs[*].Message`—your downstream parser must double-parse it.
- **`console.log()` arguments are joined with spaces** if you pass multiple arguments. Always pass a single JSON string: `console.log(JSON.stringify(entry))`, never `console.log("msg", obj)`.
- **Logpush delivery latency is ~5–10 minutes**, not real-time. R2 logs are for forensic/historical analysis, not live alerting. Use a Tail Worker streaming to Loki for near-real-time queries.
- **Logpush file naming is not guaranteed to be chronological.** Sort by last-modified date or parse the timestamp prefix in the filename when processing a directory of files.
- **R2 `DecompressionStream("gzip")` in Workers** requires the `streams` compatibility flag and Workers runtime >= 2023-03-01. Check your `compatibility_date`.
- **Logpush `sample_rate` applies to the Trace Events dataset** as a whole, not to your `console.log()` calls. Setting `sample_rate: 0.1` means 90% of requests' trace events (including all their logs) are dropped. For long-term retention use `sample_rate: 1`.

---

## Verification

```bash
# 1. Send test traffic
for i in $(seq 1 50); do
  curl -s "https://api.example.workers.dev/" > /dev/null
done

# 2. Wait ~10 minutes for Logpush delivery, then list R2 files
wrangler r2 object list logs-long-term --prefix "workers/$(date +%Y-%m-%d)/"

# 3. Download and inspect a log file
wrangler r2 object get logs-long-term "workers/$(date +%Y-%m-%d)/$(FILENAME)" --local /tmp/sample.log.gz
gzip -dc /tmp/sample.log.gz | head -5 | jq .

# 4. Verify structured JSON format
# Each line should have timestamp, level, message, ray, service, version
gzip -dc /tmp/sample.log.gz | jq 'select(.level == "ERROR")' | head

# 5. Test lifecycle rule (dry run)
curl "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/r2/buckets/logs-long-term/lifecycle" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq .

# 6. Verify redaction: search for email patterns in sample file
gzip -dc /tmp/sample.log.gz | grep -E '\b[^\s]+@[^\s]+\.' && echo "PII LEAK" || echo "OK"
```

---

## Related

- `cloudflare-logpush-r2-partitioned-athena.md` — querying R2 logs with Athena (downstream query layer)
- `cloudflare-logpush-setup.md` — Logpush fundamentals and dataset options
- `workers-logpush-observability-pipeline.md` — full Logpush observability pipeline architecture
- `workers-tail-real-time-log-streaming.md` — real-time log streaming via Tail Workers (complements R2 retention)
- `workers-tail-worker-pii-minimization-and-otel-decision.md` — PII handling before log export
- `log-retention-policies.md` — retention policy design principles
- `log-structured-logging.md` — general structured logging patterns

---

## Sources

- [Cloudflare Logpush documentation](https://developers.cloudflare.com/logs/about/)
- [Logpush to R2](https://developers.cloudflare.com/logs/get-started/enable-destinations/r2/)
- [Workers Trace Events dataset fields](https://developers.cloudflare.com/logs/reference/log-fields/account/workers-trace-events/)
- [R2 Object Lifecycle](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)
- [Cloudflare DecompressionStream in Workers](https://developers.cloudflare.com/workers/runtime-apis/streams/compressionstream/)
