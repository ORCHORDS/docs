# observability-cost-control

**Issue:** example project's observability bill is growing faster than revenue. Logs ingest tripled after a verbose dependency upgrade nobody noticed for two months, traces are ingested at 100% for a service that runs 40k RPS at peak, and the bill arrives as a single six-figure number that no team can attribute to its own services — so nobody has an incentive to fix their part of it. Telemetry costs are now a real line item (often single-digit percents of infra spend), and controlling them is an engineering discipline: filter early, sample deliberately, tier storage, and attribute cost to owners. The biggest documented lever is tail sampling that keeps 100% of errors while sampling healthy traffic, with 40–95% savings reported across the industry.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Know the bill: pricing models and attribution

1. **Read the vendor's pricing axes before optimizing.** Backends charge by ingest volume (GB or events), by GB scanned on query, by retention duration and tier, or by host/seat — Parseable's pricing guide usefully catalogs all four models. Optimizing ingest on a query-priced system, or DPU-hours when you are billed on scanned bytes, wastes effort; map every lever to the axis you are actually billed on.
2. **Attribute cost per team and service.** Tag all telemetry with `service` and `team` at the collector, and produce a monthly cost-by-derivation report (cost = ingested bytes per service × effective unit price). Dash0-style per-service cost limits only work when attribution exists; a pooled bill gives every team a tragedy-of-the-commons incentive.
3. **Alert on cost as an SLO, not just a surprise.** Log-volume spike detection (see `log-volume-spikes.md`) and daily ingest budgets per signal should page someone — a cost anomaly is an operational anomaly: it usually means a retry storm, a debug flag left on, or a cardinality explosion.
4. **Separate the three signals in the budget.** Logs, metrics, and traces have different levers and different value density; a single blended "observability spend" number hides which signal is actually bloated. Track GB/day and cost/month per signal per service.

## Filter early: the collector is the cost firewall

1. **Drop and scrub at the edge, before ingest.** OTel Collector processors (`filter`, `transform`, `redaction`, `attributes`) running before the exporter remove health-check noise, drop DEBUG logs in production, and strip high-cardinality fields and PII — OneUptime reports 40–70% volume reduction from collector filtering alone. Post-ingest filtering still pays ingest and often query costs.
2. **Drop entire classes of worthless telemetry by default.** Health check endpoints, successful synthetic probes, access logs for static assets, and repetitive framework debug lines are the standard dead weight. Maintain the drop-list in code review — every rule is a deliberate decision that someone revisits quarterly.
3. **Route by value, not by default.** Not everything deserves the expensive real-time store: high-value structured events go to the interactive backend, raw verbose logs can stream straight to cheap object storage (S3/R2) for rare forensic needs. Routing pipelines (Cribl-style) exist precisely to tier at the point of shipment.

## Sample deliberately: keep the errors, sample the boring

1. **Tail sampling is the single highest-impact lever.** Configure the OTel tail-sampling processor to keep 100% of traces with errors, latency above threshold, or specific attribute marks, and sample healthy fast traces at 1–10% — industry writeups (OpenObserve, Grepr) report 60–95% trace-bill cuts with near-zero diagnostic loss, because what you investigate is almost always an error or a slow trace. Details live in `tail-sampling-strategies.md`; the cost framing is the reason it exists.
2. **Sample logs by severity asymmetrically.** Keep ERROR/WARN at 100%; sample INFO aggressively (or derive metrics from logs and drop the raw line — see `log-derived-metrics-alerting.md`); keep DEBUG off in prod except per-service temporary toggles with expiry.
3. **Cap cardinality with a budget, not hope.** Unbounded label values (user IDs, request IDs, URLs with parameters) are a cost attack vector on metric backends; the governance process in `metrics-cardinality-budget-governance.md` and Prometheus practices in `prometheus-cardinality-management.md` keep the metric bill linear instead of exponential.
4. **Consider adaptive or head-assisted sampling for extremes.** For very high-RPS services, head sampling (drop a fixed fraction at the SDK, before collection transport) cuts collector egress cost even before tail decisions; combine with tail sampling on the remainder, and look at per-service rate limits with automatic sampling adjustment (Dash0's proposal) to enforce hard budget ceilings.

## Tier storage and retention to actual query needs

1. **Match retention to lookup probability.** Weeks-hot (interactive queries), months-warm (occasional investigations), years-cold (compliance archives in cheap object storage, queryable on demand) — Grepr and Cribl both flag default 30-day full-retention as a pure waste pattern. Compliance retention rarely requires the expensive tier, only accessibility.
2. **Pre-aggregate what you only ever chart.** If a metric is only ever viewed at 5m resolution, store the recording-rule output and let raw samples expire fast; if logs are only ever counted, the derived metric replaces them entirely after 48h.
3. **Compress and encode for the archive tier.** Columnar formats (Parquet/ZSTD) in object storage cost an order of magnitude less per GB than vendor hot storage; the trade is slower queries, which is acceptable for data touched twice a year.

## Make it a process, not a cleanup campaign

1. **Set a target ratio and review quarterly.** A common yardstick is observability spend as a bounded fraction of total infra cost (or revenue); review per-service trends with the same discipline as performance regressions. Teams with attribution and a visible ratio self-correct without central policing.
2. **Cost-check every instrumentation change in review.** A new log line at 40k RPS is ~100GB/month; the PR template asks "expected volume impact?" for any new telemetry, the same way it asks about query plans for new DB indexes.
3. **Re-verify diagnostics after every cut.** Each filter or sampling change ships with a verification: inject a known error, confirm it survives to the backend, confirm alerts still fire from the reduced stream. A cost cut that silently eats your error visibility is a delayed outage — the savings are real, so is the risk.
