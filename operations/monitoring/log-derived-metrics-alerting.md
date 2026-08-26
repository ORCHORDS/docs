# log-derived-metrics-alerting

**Issue:** Vendor appliances, legacy services, and third-party components emit no metrics — only logs — so they sit outside every dashboard and SLO, and the first sign of trouble is a customer ticket. Teams also hit signals that exist only as log events (OOM kills, leaked-credential warnings, connection resets). Deriving metrics and alerts directly from the log stream (the Loki ruler evaluating LogQL rules, or collector-side log-to-metric transforms) closes these gaps without touching application code.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When to derive metrics from logs

1. **The component cannot emit metrics.** Black-box vendor software, managed appliances, and frozen legacy services expose only their log output; the log stream is the sole telemetry surface available, so the metric must be built from it.
2. **The signal is event-shaped, not gauge-shaped.** Occurrences like leaked credentials in access logs, OOM killer messages, or TLS handshake failures are naturally counted from log lines and often cannot be instrumented as in-process metrics at all.
3. **You need alerting on high-cardinality conditions.** Extracting the metric at query time over raw logs (grouped by whatever label you need that day) avoids pre-committing unbounded label combinations to the metrics store, which is exactly the explosion `metrics-cardinality-budget-governance.md` exists to prevent.
4. **You are prototyping an alert before committing instrumentation.** A LogQL-derived error-rate alert can ship in an afternoon and prove its value; only promote it to a real SDK metric once the definition survives contact with a few incidents.
5. **Incident-time ad-hoc SLIs need dashboards fast.** During an incident, standing up a derived metric over the relevant log stream gives everyone a shared, live chart of the failure mode without waiting on a deploy to add instrumentation.

## Implementing with the Loki ruler

1. **Recording rules precompute LogQL metric queries.** The ruler evaluates expressions like `sum by (job) (rate({app="api", env="production"} |= "error" [5m]))` on an interval and stores the resulting series, optionally remote-writing them to Prometheus (v2.25+), Mimir, or a Thanos receiver so log-derived metrics sit beside native ones.
2. **Alerting rules fire straight from LogQL.** A rule such as the error-ratio query above divided by total request rate, compared to a threshold with a `for: 10m` and `severity: page` labels, routes through the standard Alertmanager path exactly like a Prometheus alert.
3. **Storage backend choice decides HA posture.** Local rule storage is read-only, single-instance, and requires identical rules mounted on every ruler pod; object storage (S3, GCS, Azure) is required for the sharded multi-ruler setup where instances coordinate through a hash ring.
4. **Respect the per-group limit semantics.** When a rule group exceeds its configured limit, Loki discards the recording samples and clears all alerts for the group while marking health as errored — a protection against runaway rules, and a state you must alert on because it silently disables the derived signal.
5. **Manage rules as code.** Use `lokitool` for format/diff/sync, the Terraform provider, or the Cortex rules GitHub Action so log-derived alert definitions are reviewed and version-controlled like every other alert, not hand-edited in a UI.

## Alternative derivation pipelines

1. **OpenTelemetry Collector filelog/stanza plus transform.** The filelog receiver ingests log files and transform processors can extract fields and emit OTLP metrics directly, which keeps the derivation inside an existing collector pipeline and works for teams standardizing on OTLP.
2. **Vector log_to_metric.** Vector's remap (VRL) parsing plus a log-to-metric node converts structured lines into counters/gauges/histograms at the shipping layer, useful when Vector is already the log agent and Loki ruler evaluation would be redundant.
3. **Grafana Alloy components.** `loki.source` plus `loki.relabel`/`loki.process` stages can normalize and label logs before they reach Loki, simplifying the LogQL the ruler has to evaluate and centralizing parsing in one place.
4. **Vendor log-to-metric features.** Datadog log-to-metric facets and similar features generate metrics at ingestion; they are the fastest path but are billed as custom metrics, so apply the same cardinality budget discipline before enabling them on high-volume streams.
5. **Recording rules over an extracted field, not regex over raw lines.** Where possible, parse once into structured labels at ingestion (`| json`) and write rules over the parsed fields, so rule evaluation is cheap and a format change surfaces as a parse-error metric rather than silent zero-matches.

## Accuracy and failure modes

1. **Parse failures silently undercount.** A JSON schema change makes `| json` drop matches and the derived rate slides toward zero without any error; always filter and track `__error__` and alert on parse-error rate so format drift is loud.
2. **Compensate for log sampling.** If logs are sampled (see `log-sampling-strategies.md`), multiply counts by the inverse sampling rate in the recording rule or via sampling-rate metadata, otherwise the derived metric reports fictional absolute levels.
3. **Absent logs are not zero traffic.** A stopped service produces no error lines, so a naive error-rate alert sees no data rather than firing; pair error signals with a volume-or-absence check (`absent()` style) so a shipping outage cannot masquerade as sudden health.
4. **Extracted labels are a cardinality vector.** Every label extracted into a recording rule multiplies stored series exactly like an SDK label; prefer grouping in the rule over labeling at ingestion, and keep unbounded values (usernames, request IDs) out of recorded labels entirely.
5. **Rule evaluation costs scale with log volume.** Metric queries over hot streams with wide time ranges are expensive; keep the `[5m]` window matched to the evaluation interval, pre-filter with stream selectors (app, env) before line filters, and monitor ruler evaluation duration as the log volume grows.
