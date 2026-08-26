# OpenTelemetry Collector memory limiter and backpressure ordering

**Issue:** An overloaded telemetry Collector can exhaust memory and be killed, causing larger gaps than controlled backpressure.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Use the Collector memory-limiter processor early in pipelines and configure limits against the container or host memory budget. It can refuse data under pressure so receivers and senders must implement the expected retry/backpressure behavior. Pair it with batching and durable queues where loss objectives require them.

## Controls and verification

- Place the limiter before processors that increase memory.
- Reserve headroom for runtime, exporters, and spikes.
- Monitor refused data, queue depth, heap, GC, and process restarts.
- Verify every receiver's retry semantics.
- Load-test sustained and burst traffic.
- Confirm overload degrades predictably without an OOM kill.

## Sources

- [OpenTelemetry Collector: memory limiter processor](https://github.com/open-telemetry/opentelemetry-collector/tree/main/processor/memorylimiterprocessor)
- [OpenTelemetry Collector: Resiliency](https://opentelemetry.io/docs/collector/resiliency/)
