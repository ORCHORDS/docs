# real-time-streaming-architecture

**Issue:** Batch pipelines cannot meet sub-minute data freshness requirements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A fraud detection system needs to act on a transaction within 500ms, but the existing hourly batch job is 59 minutes too slow.

## Pattern / Solution
Publish events to a durable message broker such as Kafka or Kinesis. Stream processors (Flink, Spark Streaming) consume and transform events continuously. Emit results to low-latency serving stores such as Redis or Pinot, or trigger downstream actions.

## Gotchas
Windowing semantics (tumbling, sliding, session windows) require careful design for out-of-order events. Watermarks manage late data. Stateful stream processing requires careful checkpoint management to enable recovery.

## Related
kappa-architecture, backpressure-patterns, event-driven-architecture
