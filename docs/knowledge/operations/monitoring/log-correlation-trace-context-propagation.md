# Log correlation and trace context propagation

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A user reports a failed API call with timestamp and error message.
The on-call engineer finds the Worker log line but cannot connect
it to the D1 query that caused the failure. Grafana shows a spike
in 500 errors but traces for those requests are missing from Jaeger.
The `cf-ray` in the Cloudflare dashboard does not appear in any
structured log. Every signal lives in a separate silo.

## Context

Log correlation attaches a shared identifier to every log line,
span, and metric emitted by all services handling a single request.
That shared key — the trace ID — lets an engineer pivot from a log
to a trace, from a trace to a D1 query plan, and from a query to
the upstream Worker span, without guessing or time-range scanning.
The W3C Trace Context standard (`traceparent` header) is the
canonical wire format. In Cloudflare Workers stacks, `cf-ray` ties
a request to edge logs and Logpush exports — complementing, not
replacing, the W3C trace ID.

## W3C traceparent header anatomy

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^^^ ^^
             |  trace-id (128-bit, 32 hex chars) parent-id(64-bit) flags
             version (always 00)
```

- **trace-id** — globally unique for the entire request chain; the
  correlation key across all log lines and spans.
- **parent-id** — the span ID of the immediate upstream caller;
  changes at each hop while trace-id does not.
- **flags** — `01` = sampled (forward spans); `00` = not sampled
  (propagate context only, do not send spans).

Parse by position, never by splitting on `-` and counting fields.
Reject malformed headers and start a fresh trace rather than
attempting repair.

## Injecting trace ID into structured logs

Every log line must carry `trace_id` as a top-level structured
field so log query tools can filter by it without full-text search.

```typescript
// Worker fetch handler — extract traceparent, attach to all logs
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const tp = req.headers.get('traceparent') ?? newTraceparent();
    const { traceId, spanId } = parseTraceparent(tp);
    const log = (level: string, msg: string, extra = {}) =>
      console.log(JSON.stringify({
        level, msg, trace_id: traceId, span_id: spanId,
        cf_ray: req.headers.get('cf-ray') ?? undefined,
        timestamp: new Date().toISOString(), ...extra,
      }));
    log('info', 'request received', { method: req.method });
    // ... handler logic ...
  },
};
```

The `cf_ray` field connects the structured log to Cloudflare's
edge logs for the same request.

## Correlating Worker logs with D1 query logs

D1 does not emit per-query traces natively. Instrument query
execution in the application layer and attach the current trace ID:

```typescript
// Wrap every D1 call with the same log function from the handler
async function tracedQuery(db, sql, params, log) {
  const t = Date.now();
  try {
    const r = await db.prepare(sql).bind(...params).all();
    log('info', 'd1 query ok',
      { sql: sql.slice(0, 120), duration_ms: Date.now() - t,
        rows: r.results.length });
    return r.results;
  } catch (err) {
    log('error', 'd1 query failed',
      { sql: sql.slice(0, 120), error: String(err) });
    throw err;
  }
}
```

Because `log` carries `trace_id`, every D1 query log is correlated
to its originating request. Query `trace_id = X` in Loki or Datadog
to see all D1 calls made during that request.

## Cloudflare Logpush correlation fields

Logpush exports Worker and HTTP request logs to R2, S3, or a SIEM.

| Field              | Description                          |
|--------------------|--------------------------------------|
| `RayID`            | `cf-ray` value — unique per request  |
| `WorkerSubrequest` | `true` for subrequest spans          |
| `Outcome`          | `ok` / `exception` / `exceededCpu`  |
| `ScriptName`       | Worker name that handled the request |

Write `cf_ray` alongside `trace_id` in every structured log line.
This lets you join Logpush exports (WAF events, cache status, TLS
version) with application logs on a single shared key.

## Building a correlation dashboard in Grafana / Datadog

**Grafana (Loki + Tempo)** — add a derived field in the Loki
datasource to turn `trace_id` values into clickable Tempo links:

```yaml
# Loki datasource settings
derivedFields:
  - name: TraceID
    matcherRegex: '"trace_id":"(\w+)"'
    url: "${__value.raw}"
    datasourceUid: tempo-uid
    urlDisplayLabel: "View trace in Tempo"
```

LogQL query to find all logs for a trace:
```logql
{job="cf-worker"} | json | trace_id="4bf92f3577b34da6a3ce929d0e0e4736"
```

**Datadog** — add `dd.trace_id` and `dd.span_id` as reserved
attributes. Datadog creates the log-to-trace link automatically.
Map the W3C hex trace ID to Datadog's decimal format:
```typescript
const ddTraceId = BigInt(`0x${traceId.slice(16)}`).toString(10);
log.info('start', { 'dd.trace_id': ddTraceId });
```

## Anti-patterns

- **Using timestamp as the correlation key** — clock skew across
  services means timestamps do not uniquely identify a request.
- **Logging trace ID only on errors** — you cannot correlate a slow
  successful request if trace ID is absent from info logs.
- **Generating a new trace ID per service** — each service must
  extract the incoming `traceparent`, not generate its own.
- **Using `cf-ray` as the only correlation key** — `cf-ray` is
  available only in Cloudflare edge logs; services outside
  Cloudflare cannot use it. Always propagate `traceparent`.

## Gotchas

- Worker `console.log` output appears in Logpush, but subrequest
  logs carry a different `RayID` than the outer request. Correlate
  subrequests via `trace_id`, not `cf-ray`.
- W3C `traceparent` is stripped by some CDN and API gateway configs
  by default. Verify pass-through in staging with `curl -v`.
- Loki's `json` parser is case-sensitive; field names in log output
  must exactly match label names in LogQL queries.
- Datadog's decimal trace ID conversion applies only to the lower
  64 bits of the 128-bit W3C trace ID.

## Verification

- Every Worker log line contains `trace_id` and `cf_ray` as top-
  level JSON fields.
- A test request with a known `traceparent` shows that trace ID in
  Loki, Tempo, and the Logpush R2 export.
- D1 query logs are queryable by `trace_id` and return all queries
  for a given request.
- Grafana derived field renders a working "View trace" link from
  every Loki log line containing `trace_id`.
- No log line in the production export contains a raw email address
  or user ID as a log field value.

## Related

- `documentation/docs/policies/monitoring/w3c-trace-context-propagation.md`
- `documentation/docs/policies/monitoring/log-correlation-ids.md`
- `documentation/docs/policies/monitoring/structured-logging-json-correlation.md`
- `documentation/docs/policies/monitoring/cloudflare-logpush-setup.md`
- `documentation/docs/policies/monitoring/grafana-loki-integration.md`

## Source URLs (verified 2026-08-17)

- W3C Trace Context specification —
  https://www.w3.org/TR/trace-context/
- Cloudflare Logpush fields reference —
  https://developers.cloudflare.com/logs/reference/log-fields/
- Grafana Loki derived fields —
  https://grafana.com/docs/grafana/latest/datasources/loki/configure-loki-data-source/#derived-fields
- Datadog log-trace correlation —
  https://docs.datadoghq.com/tracing/other_telemetry/connect_logs_and_traces/
