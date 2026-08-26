# metrics-naming-conventions

**Issue:** Metric names are written once in a hurry and read thousands of times in dashboards, alerts, and 3 a.m. queries. Without conventions a codebase accumulates http_response_time_ms, request_duration_seconds, and req_latency simultaneously; nobody knows which is authoritative, unit confusion silently corrupts rate calculations (seconds versus milliseconds bugs are endemic), and every new engineer pays a discovery tax. This article covers how to design and govern metric naming so that a name alone conveys namespace, unit, and aggregation semantics, and how to reconcile the two competing industry standards (Prometheus suffix style versus OpenTelemetry structured attributes).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Anatomy of a metric name

1. **Namespace by domain, not by team.** A leading domain segment (http_, db_, queue_, auth_) groups related series and prevents collisions; team-name prefixes fragment the same signal across reorgs and make cross-service queries impossible.
2. **One namespace convention per organization, written down.** Whether the base unit is service.domain.metric or domain_metric, pick one pattern, document it in a single page, and enforce it in review; per-repo improvisation is how the mess starts.
3. **Describe the thing measured, not the alert you plan on it.** http_server_request_duration_seconds states the measurement; http_too_slow_counter smuggles policy into instrumentation and goes stale when thresholds change.
4. **Keep names legal and portable everywhere.** Restrict to lowercase ASCII letters, digits, underscores, and dots; uppercase and hyphens work in some backends and break others, and OpenTelemetry naming rules explicitly constrain names to the portable subset.

## Units and type suffixes

1. **Prometheus convention: base units as suffixes.** Prometheus practice (and the OpenMetrics requirement) appends base-unit suffixes — _seconds, _bytes, _requests, _ratio — and exports counters with the _total suffix; rates and durations are always in base units (seconds, never milliseconds) so PromQL rate arithmetic is unit-safe.
2. **OpenTelemetry convention: units as attributes, not name text.** OTel semantic conventions prefer a structured unit and instrument type carried alongside the name, with names like http.server.request.duration; the 2024 Prometheus compatibility survey documented this as the central tension between the ecosystems.
3. **Pick one convention per pipeline and let translation layers do the rest.** OTel-to-Prometheus exporters append unit and _total suffixes automatically during conversion; hand-mixed conventions inside a single backend are what actually cause damage, because engineers cannot assume either rule holds.
4. **Never encode the unit twice or nowhere.** request_time is unfixable ambiguity; request_time_ms_v2_seconds is self-contradiction; when in doubt, follow the Prometheus base-unit rule because every query tool understands it.

## Names versus labels

1. **Do not put label values in names.** http_requests_errors and http_requests_success should be one counter with a status-class label; the two-name form cannot be summed, ratioed, or graphed coherently.
2. **Reserve labels for true dimensions.** Route, method, status class, and outcome are dimensions; anything with unbounded values (user id, full URL, session id) belongs in logs or traces, not metric labels — cardinality explosions are a naming failure mode.
3. **Share label key names across metrics.** If one metric tags method and another http_method, joining them in a dashboard becomes a mapping exercise; a short controlled vocabulary of label keys prevents this.
4. **Avoid overlapping near-duplicate metrics.** When two names measure the same thing (queue_depth and queue_size), pick one, mark the other deprecated in its description text, and delete it on a published date; documentation strings are part of the API.

## Governance that survives growth

1. **Review names like code.** Metric names are public API for dashboards and alerts; a one-line check in code review ("does this match the convention page?") costs nothing and compounds.
2. **Lint new instrumentation in CI.** Static checks can catch missing unit suffixes, uppercase letters, _total misuse, and obviously unbounded labels before they ship; this is cheaper than a post-facto migration.
3. **Register metrics in a catalog.** A simple table of name, unit, type, owner, and description — searchable — cuts discovery time and exposes accidental duplicates early.
4. **Align with semantic conventions where they exist.** OTel semantic conventions for HTTP, RPC, and database metrics exist and are converging industry-wide; adopting them for common cases means vendor dashboards and future tooling work without translation, and custom names are reserved for genuinely custom signals.

## Renaming legacy metrics

1. **Never rename silently.** Dashboards and alerts reference names as strings and break without compile errors; a rename without a migration plan is a scheduled outage of the observability system.
2. **Dual-emit through a deprecation window.** Emit old and new names together with equal values, mark the old one deprecated in its help text and catalog entry, migrate every consumer, then delete after a published date.
3. **Budget migrations like features.** A rename touching 40 dashboards and 12 alert rules is real work; tracking it in the backlog rather than doing it opportunistically prevents the half-renamed state, which is worse than either endpoint.
