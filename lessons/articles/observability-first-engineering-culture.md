# Observability-First Engineering Culture

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A production incident lasts six hours. The root cause is a subtle interaction between a
recently deployed Worker and a Durable Object's alarm handler under high concurrency. The
on-call engineer has logs but they are unstructured and inconsistent across services. There
is no distributed trace that ties the incoming HTTP request to the DO alarm that fired as a
side-effect. The metrics exist but they are measured at the wrong granularity — aggregate
p99, no per-customer or per-feature breakdowns.

The incident is eventually resolved by adding temporary `console.log` statements and
re-deploying. The six hours of downtime is not a technology failure. It is a failure of
engineering culture: the team built the feature before building the instruments to observe it.

## Context

Observability-first is a design posture, not a product category. It answers the question:
"Can I ask arbitrary questions about my system's behavior in production without deploying
new code to answer them?"

Classic monitoring is metric-based and alert-based: you define what to measure in advance
and alert when it crosses a threshold. Observability extends this with high-cardinality,
high-dimensionality telemetry (structured events, distributed traces) that allows you to
explore behavior you did not anticipate when you wrote the code.

The three pillars — logs, metrics, traces — are well-established. The cultural shift is
harder: making observability a prerequisite for merging code, not an afterthought added
post-incident.

## Pillar 1 — Structured Logs as the Foundation

Unstructured logs (`console.log("user logged in")`) are searchable by keyword but not
filterable by dimension, aggregatable by value, or correlatable across services.

Structured logs emit machine-parseable key-value pairs on every line:

```json
{
  "level": "info",
  "ts": "2026-08-22T14:23:01.432Z",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "service": "auth-worker",
  "event": "login.success",
  "user_id": "u_8f3k2j",
  "method": "email",
  "duration_ms": 42,
  "region": "EEUR",
  "cf_pop": "WAW"
}
```

Every structured log line must carry:
- `trace_id`: a correlation ID that is propagated from the inbound request through every
  downstream call, so a single customer complaint can be traced end-to-end
- `service`: the emitting service name (used to filter and group in the log platform)
- `event`: a dot-namespaced event name that is stable across deploys (used for metrics
  derivation and alert definitions)
- `duration_ms`: for any timed operation; latency distribution can then be derived without
  a separate metrics pipeline

In Cloudflare Workers, use the `waitUntil` API to flush structured logs to a backend
(Workers Analytics Engine, Logpush, or a custom ingest Worker) without holding the
response:

```typescript
ctx.waitUntil(
  logToAnalyticsEngine(env.AE_DATASET, {
    trace_id: traceId,
    event: 'login.success',
    user_id: userId,
    duration_ms: Date.now() - start,
  })
);
```

## Pillar 2 — Distributed Traces Across Service Boundaries

A single user action in a Workers architecture may touch: a Router Worker, an Auth Worker,
a Durable Object, a D1 database, a Queue, and an R2 bucket. Without a trace context
propagated across these hops, an error at the D1 layer is invisible to the engineer
looking at the Auth Worker logs.

Implement trace propagation via the W3C Trace Context standard (`traceparent` header):

1. Router Worker generates a `trace_id` and `span_id` on every inbound request
2. Every `fetch()` call to a downstream service includes `traceparent: 00-{trace_id}-{span_id}-01`
3. Every Worker receiving the header reads `traceparent`, extracts the `trace_id`, emits
   its own span with a new `span_id` and the parent's `span_id`, and propagates forward
4. Durable Object stubs and Queue consumer Workers read and propagate the same header

The trace assembly (joining spans into a waterfall) can be done in the log platform (using
the `trace_id` as the join key) without requiring an OpenTelemetry Collector if the full
OTel stack is not yet in place. Start with log-based traces; migrate to proper spans when
the platform matures.

## Pillar 3 — Metrics with the Right Granularity

Metrics fail when they are aggregated at the wrong dimension. "p99 request latency across
all Workers" hides the fact that one endpoint's p99 is 4 seconds while all others are
under 50ms.

Design metric labels before you write the code. For a Cloudflare Workers service:

| Metric | Labels |
|--------|--------|
| `http_request_duration_ms` | `method`, `route`, `status_code`, `worker_version` |
| `d1_query_duration_ms` | `query_name`, `table`, `operation` |
| `kv_operation_duration_ms` | `namespace`, `operation` |
| `queue_message_processing_ms` | `queue_name`, `outcome` |
| `do_alarm_duration_ms` | `class_name`, `outcome` |

Workers Analytics Engine is the natural destination for these metrics: it supports
high-cardinality labels (unlike traditional time-series databases that choke above 10,000
unique label combinations), is billed on writes rather than queries, and can be queried
using SQL via the Analytics Engine GraphQL API.

## Building the Culture — Observability as a Merge Gate

The cultural shift from "add logging when something breaks" to "observability before merge"
requires process enforcement, not just intent.

**In the PR template, add an observability checklist:**
- [ ] Every new code path emits at least one structured log event with `trace_id`
- [ ] Every new external call (D1, KV, R2, Queue, fetch) emits a duration metric
- [ ] Every new error path logs the error with context (not just the error message)
- [ ] New feature flag or config value is logged when read, not just when changed
- [ ] Runbook updated with the metric and log query to diagnose this code path

**In the definition of done (DoD), include:**
- A Grafana/Analytics Engine dashboard query or panel that shows the feature working
- An alert definition for the happy path (e.g., alert if the new event count drops to zero
  for more than 5 minutes in business hours)

Making observability a DoD requirement changes the conversation from "we'll add logging
later" to "the feature is not done until we can observe it."

## Runbook-Driven Observability

Every incident runbook should start with observability queries, not just remediation steps.
A runbook entry for "login service degradation" should include:

```
# Diagnose login service degradation

1. Check error rate by event type:
   SELECT event, count() FROM analytics_events
   WHERE service = 'auth-worker' AND level = 'error'
   AND timestamp > NOW() - INTERVAL '30 minutes'
   GROUP BY event ORDER BY count() DESC

2. Check per-region latency:
   SELECT cf_pop, quantile(0.99)(duration_ms) as p99
   FROM analytics_events
   WHERE service = 'auth-worker' AND event = 'login.attempt'
   AND timestamp > NOW() - INTERVAL '30 minutes'
   GROUP BY cf_pop ORDER BY p99 DESC

3. Get a sample trace for a failed login:
   SELECT * FROM analytics_events
   WHERE trace_id = '<trace_id_from_user_report>'
   ORDER BY timestamp ASC
```

Runbooks with pre-written queries reduce incident time from "spend 20 minutes constructing
a query while under pressure" to "run the query and read the result."

## Anti-patterns

**Logging at ERROR level only.** If a service emits no structured events during normal
operation, there is no baseline to compare against during an incident. Log significant
events at INFO level even when everything is working correctly.

**Using trace IDs that are not propagated.** Generating a trace ID at the Router Worker but
not propagating it to downstream Workers means the trace cannot be assembled. Propagation
is as important as generation.

**Alert on symptoms, not causes.** "p99 latency above 2 seconds" is a symptom. The cause
might be a slow D1 query, a KV miss, a third-party API, or a cold start. Symptom alerts
tell you something is wrong; cause-level metrics (D1 query duration by query name) tell
you where to look.

**Dashboard theater.** A dashboard with 30 panels that nobody looks at during an incident
is worse than no dashboard — it adds noise. Build dashboards for the three scenarios that
account for 80% of incidents. Make those dashboards the first thing on-call engineers open.

**Sampling away rare failures.** Sampling is necessary for high-volume event streams but
must be implemented carefully: never sample errors below 100%, never sample traces for
slow requests (p99+). Only sample successful, fast requests.

## Gotchas

- **Workers isolates are not always hot.** Cold starts produce anomalous latency that
  inflates p99 metrics. Tag cold-start requests using a module-scoped boolean
  (`let isFirstRequest = true`) and filter or segment cold-start spans in dashboards.

- **`console.log` in Workers goes to Cloudflare's Logpush, not to a user-controlled
  destination by default.** Without Logpush configured, logs are only visible in the
  real-time log tail (`wrangler tail`), which does not persist. Configure Logpush to a
  durable destination (R2 bucket, Analytics Engine, or an external SIEM) before going
  to production.

- **Analytics Engine has a maximum of 20 `blob` columns and 20 `double` columns per
  dataset.** Design your schema upfront; altering it later requires creating a new dataset
  and migrating historical queries.

- **The `traceparent` header is 55 characters.** Some internal fetch clients have been
  seen to drop headers over a certain length. Test that the header survives all hops in
  your service mesh before relying on it for incident diagnosis.

## Verification

Quarterly observability audit:

- [ ] All production Workers have Logpush configured and delivering to a durable destination
- [ ] 100% of requests carry a `trace_id` from entry point to all downstream services
- [ ] On-call runbooks contain pre-written queries for each service's top-5 failure modes
- [ ] Alert noise ratio (alerts fired / actionable alerts) reviewed; target < 10% noise
- [ ] Cold-start events are tagged and filterable in dashboards
- [ ] New engineers can find the root cause of a simulated incident in under 15 minutes
  using only the observability tooling (no code changes allowed)

## Related

- `ai-observability-otel-2026.md`
- `log-correlation-ids-from-day-one.md`
- `alert-fatigue-masks-real-outages-2026.md`
- `write-the-runbook-before-the-incident.md`
- `incident-response-runbook.md`
- `telemetry-sampling-must-retain-rare-failures.md`
- `monitoring-blackout-during-incident.md`

## Sources

- W3C Trace Context specification (traceparent header format)
- OpenTelemetry specification — logs, metrics, traces
- Cloudflare Workers Analytics Engine documentation
- Cloudflare Logpush documentation
- "Observability Engineering" (Charity Majors, Liz Fong-Jones, George Miranda) — O'Reilly
- Cloudflare Workers `wrangler tail` documentation
