# Agent Change Data Capture

## Scope

This article covers the capture, ordering, and downstream delivery of incremental state-change events emitted by a long-running agent. A long-running agent accumulates internal state across thousands of model invocations, tool calls, file edits, and human handoffs; downstream consumers (other agents, monitoring systems, resumable workflows, audit pipelines) need a stable, ordered, replayable view of those changes so they can resume work, reconstruct timelines, and reason about the agent's evolution.

Out of scope: full event-sourcing of the agent's prompt history, durable storage of the agent's entire conversation transcript, and observability metrics unrelated to state-change semantics. CDC is a record of mutations to durable state, not a record of every token the agent produced. It also does not cover cross-region replication or active-active multi-master consistency; CDC here is single-writer, multi-reader.

## Implementation workflow

Design the CDC stream around a small, well-typed set of change record kinds. The minimum set covers: `state.created`, `state.updated`, `state.deleted`, `tool.invoked`, `tool.returned`, `checkpoint.written`, `handoff.initiated`, `handoff.completed`, `decision.recorded`, and `error.reported`. Each record carries an opaque `entity_id` for the affected object, a monotonically increasing sequence number, a logical timestamp from a monotonic clock, a hash of the prior record to detect gaps, and an envelope that names the emitting task identity and the CDC stream partition.

Generate sequence numbers from a per-stream monotonic source. The stream itself is partitioned by task identity so that records from one task form a contiguous, ordered chain. Downstream consumers receive records in partition order; cross-partition ordering is not guaranteed and must not be relied upon. This mirrors the partition-order guarantees documented for Apache Kafka and similar log-structured systems, and aligns with the W3C Trace Context guidance that distributed work be ordered within a single trace.

Emit records transactionally with the state change whenever possible. When an agent writes to durable storage, the CDC record must be produced in the same transaction so that consumers never observe a state change without its corresponding CDC record or vice versa. If transactional emission is not feasible, use the outbox pattern: write the change record into an outbox table within the same transaction as the state change, and have a separate process drain the outbox into the stream. The agent transactional outbox article in this family describes the outbox mechanics in detail.

Tag every record with a schema version and a content type. When the agent's internal state model evolves, downstream consumers must be able to decode both old and new records during the transition window. JSON Schema 2020-12 or a similar typed descriptor gives a stable negotiation handle; the article on schema evolution compatibility covers the broader compatibility discipline.

Stream CDC records through a transport that supports at-least-once delivery with idempotent consumers. Each downstream consumer tracks its own position per partition; the consumer stores the last sequence number it has fully processed and rejects records with sequence numbers below or equal to that mark. The deduplication window is bounded; records older than the window are purged from the stream's head and must be sourced from cold storage if needed.

## Controls

Sequence numbers must be gap-detectable. Use either dense monotonic integers (where any missing number indicates a gap) or hybrid logical clocks with explicit predecessor links. Storing the hash of the prior record in each new record gives consumers a second integrity check: a record whose predecessor hash does not match the prior record's content hash indicates tampering or loss in transit.

Restrict who can write to a CDC stream. The stream's writer identity must be tied to the agent workload through a workload identity attestation such as SPIFFE, so a compromised peer cannot inject records attributed to a legitimate agent. Readers must be authenticated and authorized per stream; CDC records may contain sensitive intermediate state, so authorization should default to deny and grant least privilege.

Limit what is captured. CDC records are not a substitute for full audit logging; they are a structured mirror of durable state mutations. Free-form conversation content, reasoning traces, and personal data must be excluded or replaced with opaque references unless the consumer has an explicit need and the necessary privacy controls are in place. The privacy controls article in this family and the W3C Trace Context security guidance describe the broader treatment of PII in telemetry.

## Validation evidence

Conformance tests must cover: ordered emission within a single task, transactional emission of state change and CDC record, outbox draining under failure, schema-version negotiation, replay from a checkpoint, gap detection when records are dropped, idempotent consumption (replaying the same record twice produces the same downstream state), and cross-partition ordering behavior. Negative tests include spoofed writer identities, missing predecessor hashes, replay of records past the dedupe window, and consumer attempts to advance its position backwards.

Operational evidence includes the CDC stream's retention and lag metrics, the outbox lag between state change and CDC emission, the count of detected gaps per task, the dedupe-window eviction rate, and the proportion of records delivered within the freshness target (typically a few seconds for active tasks).

## Failure handling

When the outbox falls behind, alert operators and degrade freshness. Do not block the agent's work; instead, prioritize draining the outbox so consumers do not observe increasingly stale state. When draining cannot keep up, the system must surface a clear signal that downstream consumers may be operating on stale state and that any decisions based on CDC records should be validated against the source of truth before acting.

When the CDC stream becomes unavailable, the agent has three documented responses: (1) refuse to start new tasks until the stream is restored, (2) continue work but buffer CDC records locally with a bounded buffer, or (3) switch to a degraded mode where only critical record kinds are emitted. The choice is operation-specific and must be declared in the task policy. Default to option (2) for reversible operations and to option (1) for operations where stale state would mislead downstream consumers.

When a downstream consumer falls behind the dedupe window, it must request a full resync rather than rely on incremental CDC. The system must support a documented resync procedure that snapshots current state and replays from cold storage, even if the hot CDC records have been evicted.

## Canonical sources

- W3C Trace Context, Level 2 (ordering and propagation in distributed traces): https://www.w3.org/TR/trace-context/
- NIST SP 800-22r1 (background reference for monotonic sequence generation in audit contexts): https://csrc.nist.gov/pubs/sp/800/22/r1/final
- CloudEvents v1.0 specification (background reference for event envelope metadata): https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md
- ISO/IEC 27001:2022, Information security management (background reference for access control over audit data): https://www.iso.org/standard/27001
