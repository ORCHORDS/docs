# A2A Stream Event Ordering

## Purpose

A2A v1.0 defines ordering requirements for streamed task events so clients can reconstruct task progress without inventing their own cross-binding ordering rules.

## Core rule

Implementations must deliver streaming events in the order in which the server generated them. A transport or intermediary must not reorder status and artifact updates simply because they are buffered, retried, or handled concurrently.

This requirement applies across protocol bindings. The transport mechanism can differ, but the observable task-event sequence must preserve the server's generation order.

## Implementation guidance

1. Assign an internal monotonic sequence or equivalent ordering mechanism before handing events to transport-specific code.
2. Serialize delivery per subscription when concurrent workers can emit updates for the same task.
3. Do not assume timestamps alone provide a reliable total order; clock resolution and concurrency can produce ties.
4. Preserve ordering when adapting the same task stream to JSON-RPC/SSE, gRPC, or HTTP+JSON bindings.
5. Treat reconnect/backfill behavior separately from live ordering. If historical replay is implementation-defined, document the replay contract rather than implying guarantees the protocol does not provide.
6. Test status and artifact updates under concurrency, buffering, and slow-consumer conditions.

## Multiple streams

A2A permits multiple concurrent streams for the same task. Each subscriber still needs an ordered view of the events it receives. Implementations should avoid shared transport queues that can accidentally interleave or reorder a single subscriber's sequence.

## Sources

- A2A Protocol v1.0 specification: https://a2a-protocol.org/latest/specification/
- A2A streaming and asynchronous operations: https://a2a-protocol.org/latest/topics/streaming-and-async/

## Scope note

This article describes protocol event-ordering semantics. It does not claim exactly-once delivery, durable replay, or globally ordered events across unrelated tasks unless an implementation separately provides those properties.