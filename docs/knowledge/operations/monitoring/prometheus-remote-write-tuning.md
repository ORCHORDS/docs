# Prometheus Remote Write Tuning

Remote write turns Prometheus from a standalone database into the front door of a federated or centralized store, and it does so by replaying the write-ahead log into shard queues. Tune it correctly and the feature costs a modest, predictable overhead; tune it poorly and you get memory exhaustion, sample backlogs, or shards that thrash up and down under load. This article walks through the queue model, the levers that matter, and the relabelling and drop strategies that cut the bill before it is incurred.

## Scope

Covers the `remote_write` section of the Prometheus configuration: shard sizing via `queue_config`, retry and backoff behavior, memory implications of WAL replay, write relabelling to drop or rewrite series before they leave the process, and the observability needed to keep queues healthy. Applies to Prometheus instances sending to any remote endpoint (self-hosted, managed, or a compatible store). Excludes receiver-side concerns such as Mimir distributor limits, which are covered in the storage-focused companion article.

## Workflow or implementation guidance

Start from measured load, not defaults.

1. Establish the baseline. Read the Prometheus metrics for current ingestion — samples ingested per second and active series — and decide what subset belongs in the remote store. A surprising fraction of local series are scrape-debugging or per-instance labels nobody queries remotely; dropping them at the source is the cheapest tuning available.
2. Apply write relabelling before queue tuning. The `write_relabel_configs` block runs metric relabelling on the remote-write path only. Use `drop` actions with source labels to remove unwanted series families, and normalize or hash high-cardinality label values so the remote store sees bounded series. Order matters: relabel rules run sequentially, so a label needed by a later drop rule must survive earlier rules. Verify with the metadata API or by diffing active-series counts between the local and remote stores.
3. Size the shard queue. Remote write reads from the WAL into per-shard, in-memory buffers; each shard is a consumer with its own connection. The key parameters in `queue_config` are `max_shards` (ceiling), `min_shards` (floor, used to avoid cold-start underprovisioning), `capacity` (per-shard buffer in samples), `max_samples_per_send`, and `batch_send_deadline`. Prometheus scales shards between min and max based on backlog. Set `min_shards` high enough that steady state never needs to scale up, because scaling events drop in-flight buffers under some versions and always add jitter. Set `max_shards` as a ceiling that bounds memory: total buffered samples approximate shards times capacity, so multiply through and compare with the memory budget.
4. Set batch and deadline sensibly. `max_samples_per_send` trades batching efficiency for latency; large batches amortize HTTP overhead but delay samples and increase loss on failure. `batch_send_deadline` flushes partial batches so low-traffic queues do not stall. A common posture is batching that keeps remote-write lag under a scrape interval.
5. Configure retry for the real failure mode. `retry_backoff` bounds how long a failing shard waits before re-attempting, and `max_backoff` with the retry budget determines how long outages are survivable before samples are dropped from the WAL replay buffer. Align the retry budget with the remote store's expected worst outage.
6. Monitor the queue itself. Alert on `prometheus_remote_storage_samples_pending` and the failed/dropped counters, and on shard count pinned at `max_shards`, which means the queue is saturated and the ceiling is the bottleneck.

## Controls

- `write_relabel_configs` reviewed in change management with an expected series-count delta attached to every rule change.
- Shard floor (`min_shards`) set above observed peak concurrency so shard autoscaling events are rare; ceiling (`max_shards`) tied to a computed memory bound.
- Retry and backoff parameters documented against the remote store's outage SLO, with the survivable outage duration stated explicitly.
- Alerting on remote-write health: pending samples, failed samples, dropped samples, and shards-at-ceiling, each with a runbook entry.
- Periodic reconciliation job comparing local active series with remote active series to detect relabel drift.
- Load test gate in staging: drive double the peak ingest rate and require queues to drain within one scrape interval after the burst ends.

## Validation evidence

Tuning claims rest on numbers: a before/after table of samples-pending and shard count at fixed load; a reconciliation report showing the remote series count equals the local count minus the declared drop rules' series, with any unexplained gap investigated; and a soak test trace where a simulated backend outage lasting the retry budget produced zero dropped samples, with the drop counter incrementing only when the outage was deliberately extended past the budget. Prometheus's own remote-write metrics dashboards, captured during these tests, are the artifacts to file.

## Failure modes and correction

- Memory climbs steadily until OOM: shard capacity times shards exceeds the budget, or WAL replay after restart repopulates all queues at once. Lower `capacity` or `max_shards`, and consider `max_samples_per_send` reductions; on restart-heavy deployments, pre-warm with lower `min_shards` and accept slower catch-up.
- Shards pinned at maximum with rising pending samples: the remote endpoint, not the config, is the bottleneck. Check receiver-side rate limits, network throughput, and compression; only then raise `max_shards`.
- Remote series count drifts upward month over month: relabel rules are too permissive or new instrumentation bypasses them. Extend drop rules and reconcile counts.
- Samples arriving out of order at the store: shard-per-connection designs can reorder across shards. Confirm the store's out-of-order window covers the reorder spread, or route through a store that deduplicates.
- Silent data loss after long outages: the WAL retention window expired before samples were sent. Extend WAL retention or reduce ingest, and make the dropped-samples alert loud enough to page.

## Limitations

Queue behavior and exact `queue_config` fields vary across Prometheus versions; the configuration reference for the running version is authoritative. Memory rules of thumb here are approximations — actual footprint depends on label set sizes and WAL state. Relabelling happens after scrape, so it saves remote cost but not local ingestion cost. Remote write adds roughly a quarter more memory plus CPU and network overhead for the feature itself, per the upstream tuning guide, and no amount of tuning removes that floor. Cross-version shard-scaling edge cases mean numbers validated on one version should be revalidated after upgrades.

## Canonical sources

- Prometheus remote write tuning practices: https://prometheus.io/docs/practices/remote_write/
- Prometheus configuration reference (remote_write, write_relabel_configs, queue_config): https://prometheus.io/docs/prometheus/latest/configuration/configuration/
