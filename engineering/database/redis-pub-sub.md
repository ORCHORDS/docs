# redis-pub-sub

**Issue:** Redis Pub/Sub is fire-and-forget with no message persistence or delivery guarantee
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Using Redis Pub/Sub for inter-service communication and losing messages when subscribers are offline.

## Pattern / Solution
Redis Pub/Sub: PUBLISH channel message / SUBSCRIBE channel. Messages not persisted -- subscribers must be connected to receive. Use for real-time fanout where loss is acceptable (live dashboards, presence updates). For reliable messaging use Redis Streams or a dedicated message broker.

## Gotchas
- Subscriber that falls behind causes memory pressure -- Redis buffers output for slow clients
- No message history -- late subscribers miss prior messages
- Cluster mode: Pub/Sub broadcasts only to nodes -- use single-node for Pub/Sub

## Related
- redis-streams
- redis-data-structures
- database-change-data-capture
