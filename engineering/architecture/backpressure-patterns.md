# backpressure-patterns

**Issue:** Fast producers overwhelm slow consumers, causing unbounded queue growth
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An event stream producer sends faster than the consumer can process. Memory grows until the consumer OOMs.

## Pattern / Solution
Signal the producer to slow down when the consumer falls behind. Implement bounded queues that block or drop on overflow. Use reactive streams with demand signaling. In async systems, use queue depth metrics to trigger producer throttling.

## Gotchas
Blocking producers in synchronous pipelines can cause cascading stalls. Choose between blocking, dropping, or sampling based on the use case. Always monitor queue depth as a key metric.

## Related
throttling-patterns, load-shedding-patterns, real-time-streaming-architecture
