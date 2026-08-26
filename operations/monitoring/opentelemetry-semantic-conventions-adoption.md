# opentelemetry-semantic-conventions-adoption

**Issue:** OpenTelemetry auto-instrumentation emits span and metric attributes according to semantic conventions (semconv), and those conventions have been actively changing as the spec matures. HTTP conventions stabilized in semconv v1.23.0 (November 2023) with a breaking rename wave (http.method became http.request.method, http.status_code became http.response.status_code), and database conventions stabilized in v1.33.0 (2025) with a similar db.* to database.* shift. Teams that upgrade an SDK or collector without planning for the migration suddenly find that their dashboards, recording rules, log-derived metrics, and saved queries reference attribute names that no longer exist, producing silently empty panels and dead alerts. The engineering problem is adopting the stable conventions deliberately: running old and new attributes in parallel during transition, updating every downstream consumer, and then turning off the legacy emission without losing signal continuity.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why semantic conventions matter

1. **Portability across backends.** Semconv-compliant attribute names mean dashboards and queries written for one backend (or one service) transfer to another without renaming work, because every instrumentation library is emitting the same shapes.
2. **Free ecosystem tooling.** Backends, collectors, and connectors key features off semconv attributes: the service graph connector relies on server/client span kinds and service.name, and RED metrics from traces depend on http.request.method and http.response.status_code being present.
3. **Lower cognitive load in incidents.** During an incident, responders should not have to remember whether this particular service logs request_method, httpMethod, or http.request.method; conventions make telemetry self-describing and uniform.
4. **Stability guarantees.** Once a convention is marked stable, the project commits to not breaking it, which is what makes it safe to build long-lived alerts and SLO queries on top of those attributes.

## The migration mechanism

1. **The opt-in environment variable.** Language SDKs expose OTEL_SEMCONV_STABILITY_OPT_IN, which accepts values such as none (legacy attributes only), http (stable attributes only), and http/dup (emit both old and new names on every span). Newer SDKs add equivalent values for database conventions as they stabilize.
2. **Dual-emit first, always.** Start every migration with the dup setting so spans carry both attribute sets. This keeps existing dashboards working while you build and verify their replacements; never flip straight from legacy to stable in one change.
3. **Framework-level mirrors.** Frameworks like Quarkus expose the same switch as a config property (quarkus.otel.semconv-stability.opt-in), so teams managing config in application.properties rather than environment variables get the identical dual-emit behavior.
4. **Fixed window, not a lifestyle.** Dual emission doubles attribute volume on hot spans, which inflates ingest cost and cardinality-adjacent overhead. Treat it as a bounded transition state with an owner and a deadline, typically a few weeks per service.

## Updating downstream consumers

1. **Inventory before renaming.** Grep dashboards-as-code, recording rules, LogQL/TraceQL queries, and alert definitions for legacy names before switching anything; a missed consumer is a silently broken panel, not an error.
2. **Migrate queries in the same deploy window.** Update saved queries and alerts to the stable names while dup mode is active, verify the new queries return identical numbers side by side with the old ones, and only then remove the legacy references.
3. **Watch derived pipelines.** Collector processors (attribute renames, tail-sampling decisions, redaction rules) often match on exact attribute names; a sampling policy keyed on http.url keeps sampling everything once the attribute becomes http.url.full.
4. **Version-pin the spec you test against.** Record which semconv version your golden dashboards were validated against, because development-stage conventions (for example, GenAI conventions) can still change under you.

## Adoption guardrails

1. **Codify the setting per service.** Put the opt-in value in shared base images or Helm values rather than per-service env files, so a new service inherits the current migration state instead of defaulting to legacy without anyone noticing.
2. **Add a CI attribute check.** In integration tests, assert that emitted spans contain the stable attribute names (and, during transition, both sets), so a dependency upgrade that flips the default breaks the build instead of production dashboards.
3. **Track library defaults.** SDK and instrumentation versions decide what the default emission looks like; when upgrading several minor versions at once, read the release notes for semconv default changes before merging.
4. **Plan for the next wave.** Database conventions stabilized in 2025 and messaging conventions are on a similar track; keep the dual-emit playbook documented so the next stability announcement is routine rather than an emergency.
