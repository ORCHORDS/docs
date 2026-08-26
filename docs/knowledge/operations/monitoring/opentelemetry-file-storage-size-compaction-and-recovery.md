# OpenTelemetry File Storage Size, Compaction, and Recovery

**Issue:** Persistent queues can survive collector restarts yet leave a large bbolt file after backlog drains, exhaust local disk, or silently trade integrity for throughput.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Configure the Collector contrib `file_storage` extension on a dedicated persistent directory with explicit ownership and capacity monitoring. Set `max_size` from a disk budget; zero is unlimited and should be a conscious choice. Ensure the limit is compatible with rebound-compaction thresholds.

Choose durability deliberately. Enabling `fsync` improves integrity on interruption but costs write performance. Enable `compaction.on_rebound` when queues can grow during exporter outages and later drain. Tune the needed and trigger thresholds from observed backlog size, with enough headroom for the compaction copy. Consider startup compaction only when restart latency is acceptable.

Treat `recreate` as availability behavior, not data recovery: corruption may be renamed to a backup while the collector starts with fresh state, which can cause duplication or loss.

## Verification

1. Fill a persistent exporter queue by blocking its destination.
2. Confirm queue depth, storage file growth, and disk alerts.
3. Restore the destination and verify delivery plus online compaction after thresholds are crossed.
4. Kill the collector during load and validate the chosen fsync durability behavior.
5. Test disk-full and corrupt-copy scenarios in a disposable environment.
6. Check permissions and ensure two collectors never share the same bbolt file.

## Observability

Alert on filesystem free space, storage write errors, queue capacity, refused telemetry, export failures, and compaction/recovery logs. Correlate these signals so a recovered exporter does not hide a still-growing storage file.

## Gotchas

Compaction requires temporary space and can add I/O. Automatic recreation preserves process availability but not queued telemetry. Version-lock the Collector distribution because the extension is beta and configuration can evolve.

## Sources

- [OpenTelemetry Collector file storage extension](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/storage/filestorage)
- [OpenTelemetry Collector resilient buffering](https://opentelemetry.io/docs/collector/resiliency/)
