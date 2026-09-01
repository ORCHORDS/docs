# Loki Label Cardinality Control

In Loki, labels are not metadata attached to logs; they are the index. Every unique label set defines a separate stream, and every stream must be written, chunked, indexed, and queried as a unit. A single unbounded label — a request ID, a user ID, a pod name with a hash suffix — multiplies stream count without bound, and Loki pushes back with per-tenant stream limits, `429` rejections, and eventually a rejected-logs firehose. Controlling cardinality is therefore an ingestion architecture concern, not a labeling style preference.

## Scope

Covers the mechanics and governance of Loki label cardinality: how streams and the index relate, per-tenant ingestion limits (max streams, max global streams per tenant and per route), how to discover cardinality offenders, and how to restructure pipelines that have outgrown label-based partitioning. Applies to self-hosted Loki and Grafana Cloud Loki alike where the limits are exposed. Excludes object store sizing, query-frontend tuning, and the structured-metadata alternative beyond pointing to it (a companion article treats it fully).

## Workflow or implementation guidance

Contain cardinality in four moves: measure, bound, fix the offenders, and re-architect the outliers.

Measure first. Loki exposes per-tenant stream counts, and the cardinality analysis tooling in Grafana's Loki operational toolkit can break down stream counts by label, revealing which label contributes the most distinct values. Run this analysis on a schedule; cardinality drift is gradual and invisible until limits trip. The dashboard artifact you want is streams-per-label over time.

Bound the blast radius with per-tenant limits. The `ingester` and limits configuration expose `max_streams_per_user` and `max_global_streams_per_user` (with optional per-route overrides). These limits reject new streams when crossed — protecting the cluster at the cost of log loss for the offending producer — so set them above legitimate peaks with enough headroom that the accompanying `429` alert pages a human before sustained loss. A limit that is never approached is doing nothing; a limit that trips daily is doing harm.

Fix offenders by demoting labels to log content. A value that is unique per request, per session, or per container belongs inside the log line, not in a label. The test is simple: if a future query would filter on the value to find one event, put it in the line and parse it at query time; if queries aggregate over the value as a dimension of the system (environment, cluster, service, severity), it may be a label. Move demoted labels out of the pipeline stage that sets them, and communicate the query-pattern change, because `line` filters are slower than label matchers — that cost is the trade being made.

Re-architect the remaining outliers. Where a genuinely high-cardinality dimension must stay filterable, structured metadata is the intended mechanism: fields stored with the stream but not in the index, filterable through LogQL. Alternatively, split the highest-cardinality source into its own Loki tenant so its stream count is budgeted separately. Both routes keep the index bounded while preserving findability.

Finally, treat OTLP-sourced pipelines carefully: resource attributes promoted to labels are a common silent cardinality source, so pin the promotion allow-list explicitly in the pipeline configuration.

## Controls

- Per-tenant `max_streams_per_user` and `max_global_streams_per_user` configured with documented headroom calculations, plus per-route overrides for known bursty producers.
- Alerting on `loki_distributor_lines_received` versus rejected lines and on limit-rejection counts, with a runbook that names the cardinality analysis steps.
- Scheduled cardinality analysis (weekly) producing a streams-per-label report; any label exceeding its declared budget opens a remediation task.
- Label allow-list enforced at the pipeline layer (Alloy or Collector stage configuration) with changes reviewed like schema changes.
- Pre-production check: a new service's expected stream count (labels times value ranges) estimated and signed off before its first deployment.
- Quarterly review of per-route overrides to retire stale exceptions.

## Validation evidence

Cardinality control is evidenced by trend lines, not snapshots: the streams-per-label report showing the offending label's contribution collapsing after demotion, the per-tenant stream count stabilizing under the configured limit, and the limit-rejection counter returning to and holding zero across a full week of peak traffic. For a limits change, file the before/after rejection graph plus the headroom calculation. For a demotion, file the query-latency comparison of the replacement line-filter query, so the operational cost of the trade is visible rather than implied.

## Failure modes and correction

- `429 Too Many Requests` storms naming stream limits: a producer crossed the per-tenant limit. Identify the label via cardinality analysis, demote it, and raise the limit only as a stopgap with an expiry date.
- Index grows and queries slow even with stable stream count: chunk sizes shrink when high-cardinality labels fragment volume across streams. The fix is the same demotion; verify via the average bytes-per-stream metric.
- Silent log loss without rejections: a producer dropped logs client-side after repeated retries. Check the agent's (Alloy or Vector) delivery error metrics and the pipeline's drop counters.
- Queries time out after demotion to line filters: the dimension moved from index to scan. Add a parser stage or restructure the log format so filters run on parsed structured fields, which is faster than raw line matching.
- Label churn from pod/container identifiers: relabel away ephemeral suffixes at the pipeline stage so restarts do not spawn new streams.

## Limitations

Limits and their exact names differ between Loki versions and between self-hosted and cloud offerings; the deployed version's configuration reference governs. Demoting labels trades query speed for ingest safety, and the trade compounds: heavy line-filter usage on high-volume streams is expensive. Structured metadata requires object storage meta-information support and has its own feature maturity caveats, and very old Loki versions lack it entirely. Cardinality analysis tooling requires access to the ingester metrics and, in some setups, a dedicated diagnostic endpoint. Nothing here addresses query-time cardinality (label extraction in queries), which inflates query cost without affecting ingestion.

## Canonical sources

- Loki labels documentation (streams, cardinality best practices): https://grafana.com/docs/loki/latest/get-started/labels/
- Loki label cardinality analysis: https://grafana.com/docs/loki/latest/get-started/labels/cardinality/
- Loki LogQL log queries (line filters, parsers): https://grafana.com/docs/loki/latest/query/log_queries/
