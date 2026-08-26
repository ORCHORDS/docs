# OpenTelemetry persistent export queues and disk-failure boundaries

**Issue:** In-memory export queues lose buffered telemetry on Collector restart, while persistent queues can fail from disk exhaustion or retry expiry.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Configure a supported storage extension such as `file_storage` for selected Collector exporter sending queues when restart survival is required. Persistence is bounded durability, not guaranteed delivery: disk failure, full queues, permissions, and retry limits can still lose data.

## Controls and verification

- Put storage on a capacity-monitored persistent volume.
- Restrict permissions and consider telemetry sensitivity at rest.
- Size queue and retry windows from traffic and outage objectives.
- Monitor queue fill, failed sends, disk latency, and free space.
- Document that authentication-extension context is not persisted with queued data.
- Kill and restart a loaded Collector, then verify replay and overload behavior.

## Sources

- [OpenTelemetry Collector: Resiliency](https://opentelemetry.io/docs/collector/resiliency/)
- [Collector file storage extension](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/extension/storage/filestorage)
