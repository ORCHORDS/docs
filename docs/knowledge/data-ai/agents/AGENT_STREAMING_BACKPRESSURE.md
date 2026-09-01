# Agent Streaming Backpressure

## Scope

This article covers applying back-pressure when an agent emits streamed tokens faster than a consumer can process them. Streaming is a common pattern for agent outputs: the model produces tokens incrementally, and the consumer (a user interface, a downstream agent, or a recording pipeline) processes them as they arrive. When the consumer is slower than the producer, an unbounded buffer would let memory grow without limit and would also delay the consumer's view of the producer's intent. Back-pressure is the mechanism by which the consumer signals the producer to slow down or stop, and the producer responds by pausing emission until the consumer signals readiness.

Out of scope: the implementation of streaming transports themselves (WebSockets, Server-Sent Events, gRPC streams), the choice of token-batching strategy, and the design of UI rendering loops. This article focuses on the protocol-level contract between a streaming agent and its consumer.

## Implementation workflow

The streaming protocol must include a back-pressure channel. The channel is bidirectional: the producer signals that more data is available, and the consumer signals that it is ready to receive more (or that it must pause). A naive protocol that only flows producer-to-consumer cannot express back-pressure; the consumer must have an explicit mechanism to say "wait." This pattern is well established in reactive streams (the Reactive Streams initiative), in WebSocket flow control (RFC 9220), and in gRPC's flow-control mechanisms.

The agent emits tokens in bounded chunks rather than one at a time. A chunk size of, for example, 16 to 64 tokens is a reasonable default; the chunk size is negotiated at stream-open time and may be adjusted mid-stream by the consumer. Smaller chunks give finer-grained back-pressure but increase the protocol overhead; larger chunks are more efficient but make pause-and-resume slower. The agent must support per-chunk acknowledgment so the consumer can pace consumption.

The consumer maintains a credit window. The window is the number of chunks the consumer is willing to receive before signaling the producer to pause. The consumer refills the window as it processes chunks and pauses the producer when the window reaches zero. This is the same pattern as HTTP/2's flow control and the W3C WebTransport datagram priority model.

Cancellation semantics must be unambiguous. When the consumer cancels the stream, the producer must stop emitting promptly. The producer's cancellation handler runs synchronously or as soon as possible thereafter, releases any resources tied to the stream, and emits a final cancellation marker that downstream systems can use to confirm closure. Cancellation is distinct from pause: pause implies eventual resumption; cancellation does not.

The agent must implement a maximum stream lifetime. A streaming agent that has been emitting tokens for an unbounded duration can mask errors and consume unbounded resources. The lifetime is configurable per stream kind; for interactive user-facing streams it might be a few minutes; for batch processing streams it might be longer. When the lifetime is reached, the agent closes the stream with a `stream-timeout` error.

Stream state is observable. The agent emits `stream-opened`, `stream-paused`, `stream-resumed`, `stream-cancelled`, and `stream-closed` events. The events feed the same telemetry pipeline as trace spans. The events include the consumer identity, the chunk sizes, the credit window state at the moment of the event, and the latency between emission and acknowledgment.

## Controls

Bound the in-flight buffer. The agent must not allow its in-flight buffer to grow without limit, regardless of the consumer's back-pressure. If the consumer's credit window is not respected (for example, because of a consumer bug), the agent applies a hard cap and either pauses emission unilaterally or cancels the stream with a `consumer-overrun` error.

Privacy and data minimization. Streamed content may include sensitive information that the agent has inferred from the context. The consumer-side buffer for the stream must apply the same data minimization rules as the agent's main context window; sensitive fields are redacted or replaced with opaque references unless the consumer is authorized to see them.

Back-pressure must be respected at every hop. A multi-hop pipeline (for example, agent-to-aggregator-to-consumer) must propagate back-pressure along the chain. A hop that buffers beyond its credit window and then forwards later violates the contract with the next hop and undermines the upstream consumer's back-pressure signals. The agent is responsible for verifying that intermediate hops in its own pipeline honor back-pressure.

The stream identifier must be unguessable. A2A and similar protocols reference streams by ID; the ID must be a high-entropy value to prevent a malicious actor from guessing valid IDs and inserting or interfering with stream traffic. The A2A task identifier unguessability article in this family describes the broader discipline.

## Validation evidence

Conformance tests must cover: pause-and-resume round-trip with bounded buffer, cancellation that stops emission promptly, mid-stream chunk-size renegotiation, hard-cap behavior when consumer overruns its buffer, multi-hop back-pressure propagation, stream-timeout firing at the configured lifetime, and stream ID unguessability. Inject a slow consumer, a cancellation, and a misbehaving intermediate hop and verify the agent responds correctly.

Operational evidence includes: distribution of stream durations, distribution of chunk sizes, distribution of consumer lag (time between emission and acknowledgment), count of back-pressure events, count of cancellations, count of `consumer-overrun` events, and stream-timeout rate. Sudden changes in any of these distributions are alertable anomalies.

## Failure handling

When the consumer's back-pressure channel becomes unavailable (for example, when a WebSocket closes silently), the agent pauses emission and probes the channel with a low-frequency heartbeat. If the channel cannot be re-established within a configured timeout, the agent cancels the stream with a `consumer-unreachable` error. The cancellation is logged with the last known consumer state so post-mortem analysis can determine whether the failure was on the producer or consumer side.

When the producer's emission rate is so high that even chunked emission overwhelms the consumer, the agent applies coarser chunking and a more conservative emission rate. The adjustment is dynamic: if the consumer continues to lag, the chunk size grows and the emission rate slows. If the consumer catches up, the agent restores normal pacing. The dynamic adjustment must be bounded so the agent does not oscillate.

When a stream experiences partial failures — for example, when the connection drops after some chunks have been delivered — the consumer-side handler treats the partial state with care. The agent may offer a resumption token that the consumer can use to reconnect; the resumption token is bound to the original stream identity and carries a TTL that limits how long resumption remains valid.

When stream cancellation collides with in-flight side effects (for example, a tool call that was scheduled before cancellation), the agent must reason about the partial state explicitly. Side effects that have already been committed are not undone; side effects that are still in-flight are cancelled; the agent's audit trail records the cancellation and the state at the moment of cancellation.

## Canonical sources

- RFC 9220, Bootstrapping WebSockets with HTTP/3: https://www.rfc-editor.org/rfc/rfc9220
- W3C WebTransport specification (background reference for bidirectional stream control): https://wicg.github.io/web-transport/
- Reactive Streams Specification, version 1.0.4: https://www.reactive-streams.org/reactive-streams-1.0.4-javadoc/org/reactivestreams/package-summary.html
- IETF HTTP/2 RFC 9113, Section 5.2 Flow Control: https://www.rfc-editor.org/rfc/rfc9113#section-5.2
