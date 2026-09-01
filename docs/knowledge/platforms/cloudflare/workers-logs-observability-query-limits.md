# Workers Logs and Observability Query Limits

Workers Logs gives a Worker a place to send its logs without standing up plumbing: invocations, console output, and exceptions are captured, stored, and made queryable. The convenience hides boundaries that shape what the data can be trusted for. Sampling reduces the volume that persists, so absence of a log line is not evidence the event did not occur; query limits bound how much a single query can scan and return, so broad time ranges and loose filters fail or truncate; and retention is finite, so the window for investigating an incident closes. Knowing these boundaries turns Workers Logs from a misleading source into a dependable one.

## Scope

Covers Workers Logs and Workers observability: sampling behavior, query capabilities and limits, retention, and how these constrain incident investigation and dashboard design. Applies to teams using Workers Logs as the primary log sink for Worker workloads. Excludes Logpush to external destinations (which changes the sampling and retention calculus), exception tracking products, and Analytics Engine datasets.

## Workflow or implementation guidance

1. Decide what Workers Logs is for before relying on it: near-real-time debugging and sampling-tolerant patterns, not a complete audit trail. If a requirement is completeness — security audit, billing disputes, per-request guarantees — that requirement needs Logpush to an external sink, and the decision should be made per workload.
2. Configure observability on the Worker with explicit settings: sampling rate and the controls over what is captured (for example, whether invocation logs and headers are included). Defaults are a starting point, not a policy.
3. Structure log output deliberately: consistent, greppable message shapes with a request or correlation identifier, because sampling and query limits punish broad scans and reward tight filters. A query that filters on a specific request ID survives the limits; one that scans an hour for "error" may not.
4. Establish the query patterns you will actually need during incidents — filter by error status, by route, by request ID, by time bucket — and test each against a realistic data volume before an incident forces the test on you.
5. Respect the retention clock in runbooks: investigation steps that query logs state the query window, and anything that might be needed past retention is exported or pushed elsewhere before the window closes.
6. Measure sampling effects where it matters: for a known traffic rate, compare emitted log volume with captured volume to understand the effective sampling at your settings, and prefer client-side aggregation (counts, summaries) over raw repeated events for high-frequency signals.
7. For dashboards over Workers Logs, keep queries narrow (bounded time range, selective filters) and treat counts as estimates when sampling is active, labeling them accordingly.
8. Revisit configuration when workload volume changes by an order of magnitude: sampling settings that were fine at thousands of invocations per day behave differently at millions.

## Controls

- Purpose declaration per workload: each Worker declares whether its logs are debug-grade (sampled, Workers Logs only) or completeness-grade (Logpush configured), recorded in the service catalog.
- Sampling configuration review: sampling and capture settings are explicit and re-reviewed on major volume changes.
- Correlation identifier standard: all application log lines include a request-scoped identifier to keep queries selective.
- Query limit budget: incident runbook queries are pre-tested against realistic volume; queries known to exceed limits are rewritten before they are needed.
- Retention awareness in runbooks: every log-dependent step names its maximum lookback and the action if the window has closed.
- Estimated-count labeling: dashboards built on sampled logs label counts as estimates.

## Validation evidence

- Observability configuration as deployed (sampling rate, capture settings) per Worker.
- Query pattern test results: each runbook query executed against a production-volume dataset with timing and result completeness recorded.
- Sampling calibration measurement: emitted versus captured volume for a known traffic window, with the effective rate computed.
- Retention boundary confirmation: a query against the oldest admissible window returning data, verifying the expected retention period.
- Dashboard inventory showing which counts carry estimate labels and their sampling basis.
- Service catalog entries with the debug-grade versus completeness-grade declaration per workload.

## Failure modes and correction

- "The logs show no errors" taken as proof of none: sampling means absence is weak evidence; verify with a higher-rate sampling window for the specific query, or push complete logs for the workload in question.
- Incident query times out or truncates: narrow the time range and add selective filters (request ID, route, status); the query limit control exists so this rewrite happens in advance.
- Needed logs aged out before investigation: the retention clock won; export or Logpush earlier for completeness-grade workloads, and record the gap in the incident report.
- Noisy logging inflates cost and pushes sampling harder: reduce log volume with structured levels and aggregation so the signal that remains survives sampling.
- Console output leaking sensitive values: scrub at emission, because captured logs inherit whatever was printed.
- Dashboards asserted as exact counts: relabel as estimates or move the metric to an aggregation mechanism that is exact.

## Limitations

- Sampling applies to stored logs; completeness guarantees are not part of Workers Logs as such.
- Retention is bounded by plan and product settings; long-horizon analysis needs external export.
- Query capabilities and limits (scanned volume, returned rows, time range) constrain broad ad-hoc exploration by design.
- Effectiveness of selective querying depends on disciplined log structure, which degrades without enforcement.
- Volume-heavy Workers may see aggressive sampling at default settings, biasing rare-event visibility.

## Canonical sources

- Cloudflare Workers docs, "Workers Logs": https://developers.cloudflare.com/workers/observability/logs/workers-logs/
- Cloudflare Workers docs, "Observability": https://developers.cloudflare.com/workers/observability/
