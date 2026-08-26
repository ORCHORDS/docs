# chat-system-design

**Issue:** Real-time bidirectional messaging at scale requires specialized architecture
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A polling-based chat implementation creates thousands of unnecessary HTTP requests per second and delivers messages with multi-second delay.

## Pattern / Solution
Use WebSockets or Server-Sent Events for persistent connections. Route messages through a pub/sub layer such as Redis or Kafka so any server can deliver to any connected client. Persist messages in a time-ordered store. Implement presence tracking with heartbeats and TTL-based expiry.

## Gotchas
WebSocket connections are stateful and horizontal scaling requires sticky sessions or a shared message bus. Message ordering must be guaranteed per conversation, not globally. Offline users require a notification mechanism and message sync on reconnect.

## Related
real-time-streaming-architecture, notification-system-design, service-discovery-patterns
