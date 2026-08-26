# telemetry-pipeline-health-monitoring

**Issue:** Once observability flows through an OpenTelemetry Collector fleet, the pipeline itself becomes production infrastructure with its own failure modes: a slow backend fills the sending queue until the collector drops the oldest items to protect its memory, a bad processor config rejects spans wholesale, and an agent that silently stops scraping erodes your visibility while everything it was monitoring looks green. Worse, when the pipeline is down you cannot use the pipeline to debug itself. The engineering problem is establishing self-observability of the telemetry path: collecting the collector's own otelcol_ metrics (queue depth, failed sends, dropped items, received versus accepted rates), shipping them through an independent route, and alerting on data-loss conditions so a blind spot announces itself before an incident needs the missing data.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What the collector exposes about itself

1. **Internal telemetry under the otelcol_ prefix.** The collector emits its own metrics, logs, and traces; self-metrics like otelcol_exporter_queue_size, otelcol_exporter_queue_failed_send_items, and otelcol_exporter_send_failed_items are the primary health signals and are configured through service.telemetry.metrics readers (the modern replacement for the old metrics.address).
2. **Accepted versus received counters.** Components report both what they received and what they accepted after processing; a gap between the two means a processor (sampling, filter, redaction) or a malformed payload is discarding data, which is distinct from downstream export loss.
3. **Zpages and pprof endpoints.** The collector serves zpages for per-component diagnostics and pprof for CPU, heap, and goroutine profiles; these are the debugging surfaces when the collector itself is the incident.
4. **Sent vs failed item accounting.** The exporterhelper documents exactly how data is dropped: when an item cannot be enqueued because the queue is at capacity (or the persistent queue is full), it is dropped and counted, so data loss is always observable in metrics if you look.

## The golden signals of pipeline health

1. **Data loss rate.** Alert on any sustained increase in dropped and failed-send counters; the correct tolerance for silently lost telemetry is zero, and a rate over minutes rather than an absolute number avoids paging on single transient blips.
2. **Queue occupancy trend.** Queue depth climbing toward queue_size is the leading indicator of loss; alert on sustained high utilization (for example, above 80 percent) while there is still time to scale or shed load, not after drops begin.
3. **Pipeline throughput balance.** Compare received items to sent items per pipeline over time; a persistent divergence with no configured sampling means something is dropping data inside the collector, and a sudden collapse in received rate means an upstream producer stopped or a scrape target vanished.
4. **Process health.** Collect collector memory and CPU usage, go runtime metrics, and restart count; the documented behavior when the queue fills is dropping the oldest data to avoid running out of memory, and OOM-killed collectors take their buffers with them.

## Architecting the independent path

1. **Never ship collector self-metrics through that collector's own at-risk pipeline.** Export the fleet's self-observability through a separate route (direct Prometheus scrape of collectors, or a minimal second pipeline) so a wedged gateway cannot hide the evidence of its own failure.
2. **Scrape collectors like any other target.** Treating the collector as just another Prometheus job is the simplest robust pattern; per-collector instance labels then let you spot the one unhealthy agent in a fleet of hundreds.
3. **Keep one collector out of band.** Maintain a minimal, independently deployed collector (or direct SDK export fallback) whose health validates that the central path works, exercised with a synthetic heartbeat trace or metric.
4. **Persist queues where loss is unacceptable.** Enable the persistent queue (file_storage extension) for logs and traces tiers so backend outages degrade into disk-backed delay instead of memory-bounded drops.

## Operating the pipeline as a service

1. **Capacity alerts tied to scaling action.** Pair queue-depth alerts with an actual response: horizontal scale-out for gateways, queue_size increases for known short spikes, and documented thresholds so the on-call knows which lever to pull.
2. **Config validation and progressive rollout.** Collector config is code: validate it, version it, and roll it out gradually, because one malformed processor config applied fleet-wide is a self-inflicted total observability outage.
3. **Regular loss reconciliation.** Periodically compare item counts emitted by a sample producer against what the backend ingested; end-to-end reconciliation catches losses that no single-hop metric sees (for example, drops inside a mesh or at the vendor).
4. **Game-day the pipeline.** Deliberately stop the backend in staging and verify the expected sequence: retries fire, queue fills, alerts page, persistent queue absorbs, recovery drains — the failure mode rehearsed is the failure mode survivable.
