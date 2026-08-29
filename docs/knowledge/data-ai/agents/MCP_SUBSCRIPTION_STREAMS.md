# MCP Subscription Streams for Change Notifications

## Purpose

MCP 2026-07-28 replaces older unsolicited change-notification patterns with an explicit `subscriptions/listen` stream. Clients opt into notification types they want to receive instead of relying on a session-wide background channel.

## Guidance

1. Subscribe only to notification types the client actually handles.
2. Authenticate and authorize the subscription request independently from ordinary tool calls.
3. Re-establish subscriptions after reconnects rather than assuming transport continuity.
4. Bound queues and backpressure so a slow consumer cannot exhaust memory.
5. Treat notifications as hints to refresh state, not as authority to perform privileged actions.
6. Deduplicate or sequence notifications when downstream processing requires idempotency.
7. Close idle or abandoned streams and apply normal resource limits.

## Sources

- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP TypeScript SDK — supporting protocol revision 2026-07-28: https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28

## Scope note

Subscriptions provide an event-delivery mechanism. Application-specific consistency, replay, and durable messaging guarantees must be designed separately.
