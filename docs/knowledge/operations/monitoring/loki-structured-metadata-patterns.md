# Loki Structured Metadata and Patterns

Loki's original model forced a choice: either a field is a label, indexed and cardinality-expensive, or it lives only in the log line, cheap but discoverable only by scanning. Structured metadata splits that dichotomy — fields stored alongside each log entry but outside the index, filterable with `lineContains`-style and dedicated filter syntax without creating streams. Alongside it, the pattern language and `pattern` parser give teams a way to extract structure at query time from unstructured lines. Used together, they let a pipeline keep its index small while remaining searchable.

## Scope

Covers two related Loki capabilities: structured metadata (what it is, how to enable and send it, its filterability and limits) and pattern-based querying (the `pattern` parser grammar, the pattern query syntax for discovering recurring structures, and when parsing at query time beats storing structure at ingest). Assumes LogQL familiarity. Excludes general label cardinality governance, which a companion article covers, and excludes metric queries derived from logs.

## Workflow or implementation guidance

Adopt structured metadata for identity fields that need findability without index cost.

Start by confirming cluster support and enabling the feature: structured metadata requires object storage that supports Loki's chunk meta-information, and must be explicitly allowed in configuration before the ingester accepts it. Attempting to send structured metadata to a cluster where it is disabled results in rejected writes, so validate in staging against the same storage backend as production.

Choose fields deliberately. The correct residents of structured metadata are per-event identity fields: trace IDs, request IDs, session identifiers, span IDs. These are exactly the fields that would blow up stream count if labeled, yet are the ones engineers reach for when debugging ("show me logs for trace X"). Fields that describe the system rather than the event (cluster, service, environment) remain labels, because those are aggregation dimensions used in nearly every query and the index serves them efficiently.

Wire the pipeline to send it. With OTLP ingestion, Loki can derive structured metadata from attributes; with pipelines (Alloy stages or Promtail stage configuration), structured metadata is set explicitly. The format of the log line itself can also embed the fields, but then query-time parsing — not structured metadata — is what surfaces them, so decide which mechanism carries each field and do not duplicate.

Query with the dedicated filters. Structured metadata is filterable with the pipe filter syntax in LogQL, letting selectors narrow to entries whose metadata field matches a value, typically after the stream selector. Because it is not indexed, the filter scans; on a narrow stream that cost is small, but a broad stream selector combined with only a metadata filter is expensive. The efficient shape is a good label-level stream selector plus a metadata filter.

Use patterns for exploration and for legacy lines. The `pattern` parser extracts labeled fields from lines matching a template with capture groups — far cheaper to write than regular expressions for structured-ish text like logfmt-ish or key-value lines. The pattern query language goes further: it infers the recurring structures in a stream and reports the distinct patterns with their sample counts, which is how you discover that a "unstructured" service log is actually five message templates. The workflow is: run pattern analysis on a stream, read the dominant templates, then codify the interesting ones into `pattern` captures or a JSON log format migration.

Prefer ingest-time structure for hot paths. If a field is filtered in most queries, parsing at query time forever is paying the same scan cost repeatedly; migrating the service to structured (JSON) logging with the field as structured metadata amortizes that cost once at ingest.

## Controls

- Structured metadata allow-list per pipeline: which fields are permitted as structured metadata, declared in the stage configuration, with the list reviewed like a schema.
- Staging parity check that structured metadata writes succeed against a production-equivalent storage backend before rollout.
- Pattern-drift report: scheduled pattern query over key streams, alerting when a new dominant template appears (often the first sign of a new error class).
- Query cost review: dashboard panels whose queries rely on metadata filters or heavy parsing get a latency budget and are reviewed when stream volume grows.
- Migration ledger: for each demoted or newly added field, where it lives (label, structured metadata, line-only), so engineers know the access path.

## Validation evidence

Evidence comes in three forms. A write/read round-trip: send a controlled log batch carrying a known trace ID in structured metadata, then execute the metadata filter query and confirm exact recall of the injected entries. A cost comparison: the same discovery query executed as a line filter versus a structured-metadata filter over a fixed window, with measured query durations filed side by side. A pattern report: the output of a pattern query over a production stream showing the dominant templates and their percentages, which doubles as the baseline for drift detection.

## Failure modes and correction

- Writes rejected after adding structured metadata: the cluster has not enabled it or the object store lacks the required meta-information support. Enable per the version's configuration reference or stop sending it; the rejected-writes counter in the distributor confirms the cause.
- Filters silently match nothing: the field was placed in the line only, not in structured metadata, or the pipeline stage writes it under a different key. Verify with a raw read of one entry showing its attached metadata.
- Slow queries: a broad stream selector plus metadata-only filtering scans enormous volume. Add a narrowing label (for example, service or level) or narrow the time range; if the access pattern persists, promote the field to structured metadata at ingest if it is still line-only.
- Pattern captures misparse after a format change: templates drift when log formats change. The pattern-drift report surfaces the new template; update the `pattern` expression or push the service to structured logging.
- Version skew between agent and Loki: older agents cannot send structured metadata and drop it silently. Pin agent versions in lockstep with Loki upgrades and verify with the round-trip test after each upgrade.

## Limitations

Structured metadata is a newer capability; availability, filter syntax, and any cardinality limits on metadata itself vary by Loki version, so the deployed documentation is authoritative. It is not indexed: filters scan matching entries, so it cannot replace labels for high-selectivity aggregation dimensions. Pattern inference works best on template-like text; highly variable or binary-ish lines yield unhelpful patterns. Query-time parsing costs recur on every query and compete for frontend resources. Finally, OTLP-derived structured metadata mapping rules have evolved; revalidate the mapping when upgrading either the pipeline components or Loki.

## Canonical sources

- Loki structured metadata: https://grafana.com/docs/loki/latest/get-started/labels/structured-metadata/
- Loki labels documentation (labels versus other fields): https://grafana.com/docs/loki/latest/get-started/labels/
- Loki LogQL queries (pattern parser, filters): https://grafana.com/docs/loki/latest/query/log_queries/
