# observability-vs-monitoring

## Symptom

The team has dashboards, alerts, and a metrics pipeline — yet when production
breaks in a novel way, nobody can explain *why*. The alerts fired ("error rate
up," "latency up"), but nobody can answer: "which users are affected?", "what
did they do right before?", "what changed in the last deploy?", or "is this the
same as last week's incident?" Engineers SSH into boxes, grep logs by hand,
stitch together fragmented traces across services, and spend hours guessing.

This is the classic monitoring-without-observability trap. You have monitoring
(known-unknown dashboards for known questions) but lack observability (the
ability to ask arbitrary new questions about system behavior from outside).

## The Distinction

**Monitoring** answers "is X broken?" for a predefined set of Xs. You pick
metrics ahead of time (CPU, error rate, p99 latency), build dashboards, and set
threshold alerts. It works great for known failure modes: the DB is down, disk
is full, queue depth is climbing.

**Observability** answers "why is X behaving strangely?" for Xs you didn't
anticipate. It requires high-cardinality, high-dimensional telemetry —
structured events with rich context (user ID, request ID, feature flags, tenant,
deployment version) that you can slice, filter, and pivot ad hoc at
investigation time, without pre-declaring which slices matter.

The test: "Can a new engineer, on their first on-call shift, debug a failure
mode the team has never seen before, using only the tooling — without writing
new code or re-deploying?" If no, you have monitoring, not observability.

## Gotchas

- **"We have three monitoring tools" is not observability.** Datadog +
  PagerDuty + Grafana, each siloed, still leaves you grepping logs by hand
  during novel incidents. Observability is a property of your telemetry's
  structure and richness, not a property of which SaaS you bought.
- **Low-cardinality metrics are blind.** A metric like
  `http_requests_total{status="500"}` tells you errors are up, but not which
  endpoint, which user, which deployment, or which feature flag is involved.
  High-cardinality dimensions (user_id, request_id, trace_id, build_sha) are
  what make telemetry debuggable. Many monitoring tools charge per cardinality —
  that cost pressure pushes teams to drop the dimensions they need most.
- **Logs without correlation IDs are noise.** If every service logs
  independently with no shared trace ID, you cannot follow a request across
  services. Every log line needs the trace ID, span ID, and request ID
  propagated from the inbound request.
- **Sampling hides the bugs that matter.** Head-based sampling (decide at
  request start whether to trace) drops the slow, erroring requests because
  they're rare — exactly the ones you need. Use tail-based sampling (decide at
  request end, keep all errors and slow requests) or 100% sampling for critical
  services.
- **Dashboards age and rot.** A dashboard built 18 months ago for a service that
  has since been refactored is worse than useless — it shows stale signals and
  misleads on-call engineers. Audit and prune dashboards quarterly.
- **Alerts without runbooks cause fatigue.** An alert that fires and has no
  linked runbook forces the on-call engineer to figure out what to do from
  scratch at 3 AM. Every alert must link to a runbook with: what this means,
  how to verify, common causes, escalation path.
- **Averages hide outliers.** Reporting average latency when 1% of users see
  30-second responses averages out to "fine." Always track percentiles (p50,
  p90, p99) and look at the distribution, not the mean.
- **"Observability" vendors repackaging monitoring.** Many tools rebranded as
  "observability platforms" without adding trace correlation, high-cardinality
  event logs, or ad-hoc query capability. Evaluate on telemetry structure and
  query power, not marketing labels.

## Building Real Observability

1. **Structured logging with correlation.** Every log line is JSON with at
   minimum: `timestamp`, `level`, `service`, `trace_id`, `span_id`,
   `request_id`, `user_id` (if applicable), `build_sha`, and the event-specific
   fields. No more `console.log("got here")`.
2. **Distributed tracing end-to-end.** Propagate a trace context (W3C
   `traceparent` header) through every hop: HTTP client, message queue, DB
   driver, cron job. Every service extracts and continues the trace.
3. **Metrics with dimensions, not flat counters.** Emit metrics tagged with
   route, status, tenant, deployment, and datacenter. Verify your backend can
   query "p99 latency for route=/checkout AND deployment=v2.3 AND
   datacenter=us-east-1" without timing out.
4. **Exemplars linking metrics to traces.** When a metric spikes (error rate,
   latency), an exemplar links to a specific trace showing the slow/failing
   request. This closes the loop between "what" (metric) and "why" (trace).
5. **Service maps and dependency graphs.** Automatically generated from trace
   data, showing which services call which, with error rates and latencies on
  each edge. Updates as the topology changes — no manual maintenance.
6. **Deploy and change correlation.** Every telemetry stream should be
   annotatable with deploy events ("v2.3.1 rolled out at 14:02"). When error
   rate spikes at 14:05, the deploy annotation makes the connection obvious.

## What Good Looks Like

During an incident, an on-call engineer can, in under 5 minutes and without
leaving the observability UI:
- Find the spike on the error-rate dashboard
- Click through to affected traces, filtered to the failing route
- See the exact user, the exact parameters, the downstream call that timed out
- Correlate the spike's timestamp to a recent deploy
- Share a permalink to the trace with the team in Slack

If that workflow isn't possible, the gap is observability, not tooling budget.
