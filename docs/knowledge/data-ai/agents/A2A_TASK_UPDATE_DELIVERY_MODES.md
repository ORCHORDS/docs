# A2A Task Update Delivery Modes

## Purpose

A2A supports several ways for a client to receive task progress and completion updates. Choosing among polling, streaming, and push notifications should depend on latency, connectivity, capability support, and operational constraints rather than assuming one delivery mode fits every workflow.

## Delivery modes

### Polling

Clients call Get Task periodically. Polling works across protocol bindings and restrictive network environments, but it can add latency and unnecessary requests when updates are frequent.

### Streaming

Streaming delivers task status and artifact updates as they occur. It is suited to interactive clients and real-time progress views, but requires the agent to advertise streaming capability and requires a persistent streaming connection.

### Push notifications

Push notifications deliver task updates asynchronously to a client-registered webhook. They suit long-running or disconnected scenarios and require explicit push-notification capability and secure webhook handling.

## Practical controls

1. Check the Agent Card capability before using streaming or push-notification operations.
2. Use polling intervals that balance freshness with server load.
3. Treat streamed, polled, and pushed task states as different delivery paths for the same underlying task lifecycle.
4. Make update processing idempotent because asynchronous delivery can be repeated.
5. Re-authenticate or authorize task access for every retrieval or subscription mechanism.
6. Do not expose task data merely because the caller possesses a task identifier.
7. Define reconnection and missed-update behavior explicitly for streaming clients.

## Sources

- A2A Protocol — current specification, Task Update Delivery Mechanisms: https://a2a-protocol.org/dev/specification/
- A2A Protocol — current specification, asynchronous processing and capability validation: https://a2a-protocol.org/dev/specification/

## Scope note

The protocol defines delivery mechanisms; retry timing, persistence, queueing, webhook infrastructure, and client user-experience policy remain implementation choices.
