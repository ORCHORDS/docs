# Cloudflare Logpush Custom Fields Workers Dataset

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to ship additional request/response metadata — request body digests,
custom request headers, Worker-computed labels, A/B test bucket assignments —
to your SIEM or data warehouse via Logpush.  The default `http_requests`
dataset does not include these fields, and appending them via a separate logging
path creates a join problem.  The Logpush **Workers trace** dataset combined
with `Custom Fields` lets you embed arbitrary key-value pairs directly into
Logpush records.

---

## Context

Cloudflare Logpush supports multiple datasets.  The two most relevant for
Workers-enriched logging are:

| Dataset name | What it contains |
|---|---|
| `workers_trace_events` | Per-invocation traces for every Worker request |
| `http_requests` | L7 HTTP request logs with standard CDN fields |

**Custom Fields** is a Logpush feature that allows you to inject up to 10
additional header-based values from the origin response (for `http_requests`)
or from a Workers `console.log` structured payload (for `workers_trace_events`)
into your Logpush records.

For Workers, the mechanism is:
1. Your Worker emits structured logs using `console.log(JSON.stringify({...}))`.
2. A Tail Worker or the built-in Workers Trace collector captures those events.
3. A Logpush job targeting `workers_trace_events` ships them, including the
   `Logs[].Message` array, to your destination.

For HTTP request logs, Custom Fields are configured via the Logpush job and
extract specific **request** or **response** headers by name.

---

## Configuring HTTP Request Logpush with Custom Fields

### Step 1 — Identify which response headers to capture

Your origin (or a Worker) must attach custom headers to responses for Logpush
to pick them up:

```typescript
// Worker that injects custom headers for Logpush Custom Fields
export default {
  async fetch(request: Request): Promise<Response> {
    const response = await fetch(request);

    const headers = new Headers(response.headers);

    // Logpush Custom Fields read these response headers
    headers.set("X-AB-Bucket", getABBucket(request));
    headers.set("X-Request-Tenant", getTenantId(request));
    headers.set("X-Cache-Tier", getCacheTier(request));

    return new Response(response.body, { status: response.status, headers });
  },
};

function getABBucket(req: Request): string {
  // Deterministic bucket based on IP hash
  const ip = req.headers.get("cf-connecting-ip") ?? "0.0.0.0";
  let hash = 0;
  for (const c of ip) hash = (hash * 31 + c.charCodeAt(0)) >>> 0;
  return hash % 2 === 0 ? "control" : "treatment";
}

function getTenantId(req: Request): string {
  return req.headers.get("X-Tenant-Id") ?? "unknown";
}

function getCacheTier(req: Request): string {
  return req.headers.get("CF-Cache-Status") ?? "UNKNOWN";
}
```

### Step 2 — Create a Logpush job with custom fields

```bash
# Create Logpush job that includes custom response header fields
curl -sS -X POST \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset": "http_requests",
    "name": "http-requests-with-custom-fields",
    "destination_conf": "r2://<YOUR_BUCKET>/http-requests?account-id=<ACCOUNT_ID>",
    "output_options": {
      "field_names": [
        "ClientRequestURI",
        "ClientIP",
        "EdgeResponseStatus",
        "CacheStatus",
        "EdgeStartTimestamp",
        "ResponseHeaders"
      ],
      "response_fields": [
        "X-AB-Bucket",
        "X-Request-Tenant",
        "X-Cache-Tier"
      ]
    },
    "logpull_options": "fields=ClientRequestURI,ClientIP,EdgeResponseStatus,CacheStatus,EdgeStartTimestamp,ResponseHeaders&timestamps=rfc3339"
  }' | jq .
```

---

## Workers Trace Events Dataset with Structured Logs

For Worker-side business logic metadata, use `workers_trace_events`.  Your
Worker emits structured JSON via `console.log`; Logpush ships it alongside the
invocation metadata.

```typescript
// src/index.ts  — structured logging for Logpush workers_trace_events
export interface Env {
  ENVIRONMENT: string;
}

interface RequestLog {
  event: string;
  requestId: string;
  path: string;
  method: string;
  tenantId: string | null;
  abBucket: string;
  durationMs?: number;
  status?: number;
  environment: string;
}

function generateRequestId(): string {
  return crypto.randomUUID();
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const startMs = Date.now();
    const requestId = generateRequestId();
    const url = new URL(request.url);
    const tenantId = request.headers.get("X-Tenant-Id");
    const abBucket = request.headers.has("X-Force-Bucket")
      ? (request.headers.get("X-Force-Bucket") as string)
      : Date.now() % 2 === 0 ? "control" : "treatment";

    // Emit structured log — captured by workers_trace_events Logpush dataset
    const baseLog: RequestLog = {
      event: "request_start",
      requestId,
      path: url.pathname,
      method: request.method,
      tenantId,
      abBucket,
      environment: env.ENVIRONMENT,
    };

    // console.log in Workers emits to the trace collector
    console.log(JSON.stringify(baseLog));

    let response: Response;
    try {
      response = await handleRequest(request, env, { requestId, tenantId, abBucket });
    } catch (err) {
      console.log(
        JSON.stringify({
          ...baseLog,
          event: "request_error",
          error: String(err),
          durationMs: Date.now() - startMs,
        }),
      );
      return new Response("Internal Server Error", { status: 500 });
    }

    console.log(
      JSON.stringify({
        ...baseLog,
        event: "request_complete",
        status: response.status,
        durationMs: Date.now() - startMs,
      }),
    );

    return response;
  },
};

async function handleRequest(
  request: Request,
  env: Env,
  meta: { requestId: string; tenantId: string | null; abBucket: string },
): Promise<Response> {
  // Application logic here
  return new Response(JSON.stringify({ requestId: meta.requestId }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

### Creating the Workers Trace Events Logpush job

```bash
# Workers trace events job — ships to R2; logs include console.log payloads
curl -sS -X POST \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "dataset": "workers_trace_events",
    "name": "workers-trace-custom-fields",
    "destination_conf": "r2://<YOUR_BUCKET>/workers-traces?account-id=<ACCOUNT_ID>",
    "output_options": {
      "field_names": [
        "Event",
        "EventType",
        "EventTimestampMs",
        "Outcome",
        "Logs",
        "ScriptName",
        "Exceptions"
      ],
      "timestamp_format": "rfc3339"
    },
    "enabled": true
  }' | jq .
```

---

## Parsing Workers Trace Logs in R2 (Athena / DuckDB)

Each Logpush record is a NDJSON line.  The `Logs` field is an array of
`{Level, TimestampMs, Message}` objects where `Message` is an array of
stringified values.

```sql
-- DuckDB: extract custom fields from workers_trace_events shipped to R2
SELECT
  EventTimestampMs,
  ScriptName,
  Outcome,
  logs.Message[1]::JSON->>'$.requestId' AS request_id,
  logs.Message[1]::JSON->>'$.tenantId'  AS tenant_id,
  logs.Message[1]::JSON->>'$.abBucket'  AS ab_bucket,
  logs.Message[1]::JSON->>'$.durationMs'::INTEGER AS duration_ms,
FROM
  read_ndjson_auto('s3://your-bucket/workers-traces/*.log.gz')
  , unnest(Logs) AS t(logs)
WHERE
  logs.Message[1]::JSON->>'$.event' = 'request_complete'
  AND EventTimestampMs > epoch_ms(now() - INTERVAL '1 day');
```

---

## Tail Worker Pattern for Real-time Custom Field Fanout

If you need low-latency custom field forwarding without waiting for Logpush
batch intervals, use a Tail Worker:

```typescript
// tail-worker/src/index.ts
export interface Env {
  ANALYTICS_ENDPOINT: string; // e.g. Workers Analytics Engine or external
}

export default {
  async tail(events: TraceItem[], env: Env): Promise<void> {
    for (const event of events) {
      for (const log of event.logs) {
        let parsed: Record<string, unknown>;
        try {
          parsed = JSON.parse(log.message[0] as string);
        } catch {
          continue;
        }
        if (parsed.event === "request_complete") {
          await fetch(env.ANALYTICS_ENDPOINT, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              timestamp: log.timestamp,
              scriptName: event.scriptName,
              outcome: event.outcome,
              ...parsed,
            }),
          });
        }
      }
    }
  },
};
```

---

## Anti-patterns

- **Logging sensitive PII in `console.log`** — `workers_trace_events` is
  shipped in plaintext to your destination.  Never log tokens, passwords, card
  numbers, or full request bodies.
- **Using more than 10 response_fields** — Logpush silently truncates custom
  response fields beyond 10.  Consolidate multiple values into a single header
  (JSON-encoded) and parse on the destination side.
- **Non-JSON `console.log` messages** — Logpush stores `Logs[].Message` as a
  string array; non-JSON strings cannot be queried with `->>'$.field'` syntax.
  Always use `console.log(JSON.stringify({...}))`.
- **Creating a per-zone workers_trace job for account-scoped Workers** —
  `workers_trace_events` is an account-level dataset; the job goes under
  `/accounts/{account_id}/logpush/jobs`, not zones.
- **Forgetting `"enabled": true`** — Logpush jobs are created **disabled** by
  default.  Verify with a GET and set `enabled: true` to start shipping.

---

## Gotchas

- Logpush has a **minimum batch interval of 30 seconds** and a maximum
  observed delay of ~5 minutes.  It is not a real-time stream.  Use Tail
  Workers for latency-sensitive use cases.
- Custom response fields in `http_requests` capture the value **as seen at the
  edge after Workers runs**.  If your Worker strips a header before the response
  reaches the edge, it will not appear in Logpush.
- The `Logs` field in `workers_trace_events` is limited to the first **~100**
  console messages per invocation.  High-frequency logging gets truncated.
- Workers running on the **Free plan** do not emit `workers_trace_events` to
  Logpush.  This feature requires a Workers Paid plan.
- R2 as a Logpush destination requires an R2 API token with `Object:Write`
  permission on the bucket; the zone API token alone is insufficient.

---

## Verification

```bash
# List Logpush jobs for a zone
curl -sS \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.result[] | {id, dataset, name, enabled}'

# List account-level jobs (workers_trace_events)
curl -sS \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/jobs" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.result[] | {id, dataset, name, enabled}'

# Enable a disabled job
curl -sS -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/jobs/${JOB_ID}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}' | jq .
```

---

## Related

- `workers-logpush.md` — foundational Logpush Workers setup and destination
  options
- `workers-tail-workers.md` — real-time log fanout as a complement to Logpush
- `logpush-subrequest-merging-completeness.md` — why subrequest logs appear
  merged and how to distinguish them
- `cloudflare-ai-gateway-logs-analysis-logpush-r2.md` — end-to-end example of
  Logpush to R2 for AI Gateway logs
- `workers-analytics-engine.md` — lower-latency alternative for custom metrics
  that does not require Logpush

---

## Sources

- Logpush Custom Fields:
  https://developers.cloudflare.com/logs/reference/custom-fields/
- Workers Trace Events dataset fields:
  https://developers.cloudflare.com/logs/reference/log-fields/account/workers_trace_events/
- Logpush job creation API:
  https://developers.cloudflare.com/api/operations/post-accounts-account_identifier-logpush-jobs
- R2 as Logpush destination:
  https://developers.cloudflare.com/logs/get-started/enable-destinations/r2/
