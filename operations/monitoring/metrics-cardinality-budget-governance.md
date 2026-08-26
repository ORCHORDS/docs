# metrics-cardinality-budget-governance

**Issue:** A single deploy adds a `user_id` label to one counter and the observability bill or Prometheus memory doubles overnight; the outage-or-overcharge cleanup repeats every quarter because cardinality is treated as a server-side technical problem rather than a budgeted, CI-enforced resource. This article covers preventing cardinality at the instrumentation source, detecting overflow early, and operating per-team cardinality budgets with cost attribution, complementing the server-side Prometheus techniques in `prometheus-cardinality-management.md`.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Prevention at the source

1. **Strip unbounded attributes with SDK Views.** OpenTelemetry Views let each metric stream drop or normalize attributes before export; raw URLs, request/session IDs, user input, and free-text error messages should never reach a metric stream because they create one series per unique value.
2. **Emit route templates and bounded categories.** Instrument with `http.route` templates, numeric status codes, and a fixed set of error categories instead of raw paths or exception messages; a dimension that helps logs and traces does not automatically belong on metrics.
3. **Default to a short dimension allowlist per metric.** Define the intended dimensions when a metric is introduced (method, route, outcome) and make additions an explicit review decision, so cardinality growth is a choice rather than an accident of attribute leakage.
4. **Size legitimate limits deliberately.** If a dimension is operationally necessary (for example active tenants), calculate the expected simultaneous combinations (tenants x routes x outcomes), configure the SDK limit with headroom, and use delta temporality so only the bounded active set per collection cycle counts toward series rather than every value ever seen.
5. **Put new labels/dimensions on the code-review checklist.** The cheapest place to kill cardinality is the pull request; a standing review item asking "does this attribute have a bounded value set?" costs seconds and prevents the incident entirely.

## Detection and safety nets

1. **Alert on SDK overflow, not just on bill spikes.** When a stream exceeds its cardinality cap (default 2000 unique attribute combinations per metric stream), the SDK folds new values into an overflow data point marked `otel.metric.overflow=true`; alert continuously on `last_over_time({otel_metric_overflow="true"}[5m])`, paging for SLO-critical metrics and ticketing the rest.
2. **Understand what overflow silently breaks.** Totals stay correct on the overflow point, but any grouped or filtered query undercounts for *all* attributes on that stream, including low-cardinality ones like a boolean success flag, so overflow must be treated as a data-quality incident rather than a curiosity.
3. **Keep a centralized collector guardrail.** A filter processor in the shared OpenTelemetry Collector pipeline that drops known-bad metric/attribute combinations acts as defense-in-depth for teams whose SDK config slips through review, before data reaches a per-series-billed backend.
4. **Watch backend usage dashboards weekly.** Vendor usage APIs (Datadog custom-metrics usage, Mimir/Grafana cardinality APIs) turn "series count" into a number someone owns; review the top growth metrics weekly so a 10x jump is caught in days, not at invoice time.
5. **Pair with the memory limiter as a circuit breaker.** Runaway cardinality drives collector memory first; the memory_limiter processor refuses/refuses-and-drops under pressure so a single team's explosion degrades their signal instead of the shared pipeline.

## Operating a cardinality budget

1. **Assign each team an active-series budget.** Give every owning team a number (active series, or attributed custom-metric cost) sized to their service count and traffic, making "my metric is expensive" a bounded, negotiable resource instead of an open-ended surprise.
2. **Enforce budgets in CI via monitoring-as-code.** When alerts, recording rules, and instrumentation config live in git, a pipeline check can diff expected series counts and block merges that exceed a team's budget without a documented exception, mirroring the workflow in `monitoring-as-code.md`.
3. **Do chargeback or showback by owning team.** Tag metrics and pipelines with a team label and attribute backend cost per owner each month; visible cost changes behavior faster than any architecture diagram about time-series databases.
4. **Run a weekly top-10 growth review.** A standing 15-minute review of the fastest-growing metrics and their owners catches slow leaks (new deployments, new regions, churned series) that overflow alerts miss because they never quite trip the cap.
5. **Expire exceptions.** When a team legitimately exceeds budget (a migration, an experiment), grant the exception with an expiry date and a review ticket, so temporary cardinality does not silently become permanent baseline.

## Choosing the right signal for high-cardinality data

1. **High-cardinality context belongs in traces and logs.** User IDs, request IDs, and cart contents are queries you run *after* something breaks; keep them in traces/logs where they are searchable per-request, not in metrics where every distinct value costs a series forever.
2. **Use exemplars for per-request links from metrics.** Exemplars carry representative trace IDs on histogram and counter points (see `opentelemetry-exemplars-metric-to-trace-links.md`), providing the "drill into one real request" capability without any label growth.
3. **Derive metrics from traces at the collector instead of pre-emptively labeling.** The spanmetrics connector converts already-paid-for spans into RED metrics, so new per-service dashboards need zero new SDK labels and their dimension set is centrally governed.
4. **Aggregate in the collector when the raw dimension is only needed transiently.** A transform/group-by-attribute processor can roll rare values into an `other` bucket before export, preserving totals and top-N usefulness while capping backend series.
5. **Re-evaluate dimensions quarterly against actual queries.** Grep dashboards and alert rules for each label on a metric; a dimension nobody queries is pure cost, and removing it is the rare optimization that reduces both bill and cognitive load.
