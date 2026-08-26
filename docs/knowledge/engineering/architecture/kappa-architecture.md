# kappa-architecture

**Issue:** Lambda architecture's dual codepaths cause maintenance overhead
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A batch layer and a streaming layer implementing the same business logic diverge after six months, producing different results for the same queries.

## Pattern / Solution
Eliminate the batch layer. Store all events in a durable, replayable log such as Kafka. Process everything through the stream processor. Reprocess history by replaying the log from the beginning into a new output topic or table.

## Gotchas
Reprocessing large historical logs can take hours. The stream processor must be idempotent and handle out-of-order events. Log retention cost increases with reprocessing requirements.

## Related
lambda-architecture, real-time-streaming-architecture, event-sourcing-pattern
