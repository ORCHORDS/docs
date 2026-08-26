# Prometheus remote-write queue capacity and shard tuning

**Issue:** Increasing remote-write parallelism to fix lag can overwhelm the receiver or exhaust Prometheus memory while leaving the actual bottleneck unresolved.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Prometheus creates a queue per remote-write destination, reads samples from the WAL, and sends them through dynamically managed shards. Tune `queue_config` from observed ingestion rate, pending samples, send latency, failures, receiver capacity, and memory headroom.

Capacity is per shard. Memory therefore grows with shard count and the sum of queue capacity and batch size. Prometheus recommends capacity sufficient for several requests and documents a typical relationship of roughly three to ten times `max_samples_per_send`, but workload measurement remains authoritative.

## Operational controls

- Alert on pending and failed samples, shard saturation, WAL lag, retries, memory, CPU, and network use.
- Increase receiver throughput or reduce unnecessary samples before raising `max_shards`.
- Bound `max_shards` to protect both Prometheus and the remote endpoint.
- Tune batch size against receiver limits and latency objectives.
- Plan for extended receiver outages; WAL retention and compaction bound how long unsent data remains recoverable.
- Change one related parameter set at a time and record before/after metrics.

## Verification

1. Establish baseline ingest rate, send rate, pending samples, active shards, and memory.
2. Load test with production-like series churn and label sizes.
3. Introduce receiver latency and failures and observe queue recovery.
4. Confirm recovery does not overload the receiver after an outage.
5. Validate alerts early enough to act before the retention window is exhausted.

## Sources

- [Prometheus: Remote write tuning](https://prometheus.io/docs/practices/remote_write/)
- [Prometheus: Configuration — remote_write](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#remote_write)
- [Prometheus: Remote write specification](https://prometheus.io/docs/specs/prw/remote_write_spec/)
