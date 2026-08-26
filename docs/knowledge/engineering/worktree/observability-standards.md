# observability-standards

**Issue:** Every team instruments its services differently: one uses structured logs, another printf; metrics are named by personal convention; traces exist in one service and not its callers. During incidents, engineers mentally correlate three dashboards that share no identifiers, and questions as basic as "which requests failed and why" take an hour to answer. Observability standards fix this by making telemetry a platform with shared contracts rather than a per-team craft. The industry consolidated decisively around OpenTelemetry (OTel), which by 2025 had moved past early adoption to become the de facto vendor-neutral standard for logs, metrics, and traces — meaning standards are now less about inventing conventions and more about adopting OTel's semantic conventions and pipeline patterns consistently.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Signals and instrumentation

1. **Adopt OpenTelemetry as the single instrumentation standard.** OTel provides one API and SDK across languages for all three signals, freeing the backend choice (vendor migration becomes a config change, not a rewrite). New services should be born instrumented; a shared baseline library in each language makes the default path the easy path.
2. **Prefer auto-instrumentation where it exists.** Web frameworks, HTTP clients, and databases have mature automatic instrumentation; hand-rolled metrics around every handler are a maintenance liability. Reserve custom instrumentation for business events auto-instrumentation cannot see.
3. **Emit all three signals with trace context in logs.** The debugging payoff comes from correlation: every log line carries its trace and span IDs, so an incident investigation moves from a failing request to its distributed trace to its log context without grep archaeology.
4. **Standardize on structured, leveled logging.** JSON logs with consistent fields (timestamp, service, severity, trace_id, and a small agreed event vocabulary). Free-text logs are unqueryable at exactly the moment they matter most.
5. **Log events, not narratives.** Emit machine-parseable facts at meaningful state transitions rather than prose. Narrative debugging belongs in the investigation document, not the log pipeline.

## Semantic conventions and resource attributes

1. **Use OTel semantic conventions for names.** Standard attribute names (http.request.method, db.operation.name, service.name, deployment.environment) make telemetry queryable across teams on day one. Local dialects are the root cause of cross-team dashboard spaghetti.
2. **Require a mandatory resource attribute set.** Every telemetry emitter must attach service name, version, environment, and owning team. The owning-team attribute is what routes alerts and postmortem questions to the right humans automatically.
3. **Define a small cardinality contract.** Attribute values must be bounded: user IDs, request bodies, and unbounded status strings do not belong as metric label values. Publish the cardinality limits in the standards doc and enforce them in review, because cardinality explosions are a billing incident.
4. **Version breaking telemetry changes.** When a metric or attribute semantics change, document it and coordinate consumers — dashboards and alerts silently break otherwise.

## Pipelines and cost control

1. **Route everything through an OTel Collector.** A central collector pipeline (application to collector to backends) decouples producers from backends, provides a control point for filtering, enrichment, and redaction, and is the standard 2025 deployment pattern.
2. **Sample deliberately, and prefer tail-based.** Head-based sampling drops interesting and boring traces at equal rates; tail-based sampling at the collector keeps the errors and slow requests while dropping the boring majority, which controls cost without blinding debugging.
3. **Redact at the pipeline, not by hope.** Secrets, tokens, and personal data must be scrubbed in the collector processors before any backend sees them. Post-hoc scrubbing after a leak is not a control.
4. **Treat telemetry spend as an engineering metric.** Review per-service telemetry volume monthly alongside other cost lines; runaway ingest is usually one unbounded attribute away.

## Alerting philosophy

1. **Alert on symptoms users feel, tied to SLOs.** Alerts should fire on burn rate against service level objectives, not on every resource wobble. If an alert does not require a human action, it belongs on a dashboard.
2. **Route alerts by the owning-team attribute.** Ownership metadata on telemetry makes alert routing automatic and eliminates the "who owns this dashboard" incident ritual.
3. **Minimize false positives ruthlessly.** Alert fatigue is the failure mode that quietly disables the whole observability investment; every alert that pages should be tuned until it deserves the page.

## Ownership and lifecycle

1. **Make telemetry part of the definition of done.** A service is not done until it emits the standard signal set with standard attributes and its dashboards render — enforced through the production readiness review, not memory.
2. **Assign each dashboard and alert an owner.** Unowned dashboards rot into misinformation; quarterly sweeps delete alerts nobody remembers creating and dashboards that reference dead services.
3. **Test the pipeline in staging with the same shape as production.** A telemetry pipeline that silently drops data is discovered during the worst possible week; inject known traffic and verify end-to-end.
4. **Review the standards doc twice a year.** OTel semantic conventions evolve; the standards doc should track the stable ones and prune local conventions that upstream has replaced.
