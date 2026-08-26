# claim-check-pattern-large-messages

**Issue:** Event-driven systems break in predictable ways when messages carry large payloads — multi-megabyte JSON documents, base64-encoded media, or embedded report blobs. Message brokers degrade badly above a few hundred kilobytes: Kafka's default `max.message.bytes` is 1 MB and raising it strains brokers, controllers, and consumers alike; SQS caps at 256 KB and charges per request regardless of size; RabbitMQ queues balloon and page to disk; NATS drops to disk-bound throughput. Meanwhile consumers usually need only a handful of fields to route the message, and full payloads force every subscriber to deserialize data they will never read. The claim-check pattern (documented by Microsoft in its cloud design patterns catalog and standard practice in AWS and Azure messaging guidance) solves this by splitting the message into a small envelope on the bus and the full payload in object storage, joined by a reference.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the Pattern Works

1. **Split at the producer.** Before publishing, the producer serializes the full payload, writes it to cheap durable blob storage (S3, R2, Azure Blob, GCS), and publishes an envelope containing only routing metadata plus a storage reference — bucket, key, and optionally a checksum and content length.
2. **Reference shape matters.** Prefer opaque, unguessable keys (UUIDs or content hashes) over user-derived filenames. A content-hash key (for example the SHA-256 of the payload) gives you free deduplication when producers retry, because identical payloads land at the same key.
3. **Fetch on demand at the consumer.** Subscribers that only need routing fields skip the download entirely; subscribers that need the body perform a ranged GET. This is the core economic win: you pay the network and deserialization cost exactly where the data is used.
4. **Keep the envelope self-sufficient.** Include enough metadata (event type, version, aggregate ID, content type, byte size, checksum) that consumers can decide whether to fetch, validate integrity after fetching, and reject oversized or corrupted payloads defensively.
5. **Define the read contract.** Decide upfront whether the reference is readable by the consumer directly (pre-signed URL, public-with-key) or must be fetched through an internal service that enforces access control and audit logging. Broker permissions and storage permissions are two different security domains.

## Lifecycle and Garbage Collection

1. **Blobs outlive messages by design.** The bus deduplicates and expires messages quickly; the claim-check payload must survive long enough for slow consumers, replay scenarios, and dead-letter retries — typically hours to days, not minutes. Decouple the two retention windows deliberately.
2. **Lifecycle rules beat deletion hooks.** Configure storage lifecycle policies (expire after N days, transition to infrequent-access tiers) rather than having the last consumer delete the blob. Racing consumers and redeliveries make "delete when done" a correctness bug.
3. **Handle orphaned envelopes.** A consumer must tolerate a 404 on fetch: the blob expired, the lifecycle rule fired early, or cross-region replication lagged. Treat it as a poison message, dead-letter it with the reason, and never silently retry forever.
4. **Replay needs a plan.** Replaying old events requires the blobs to still exist. If compliance forces short blob retention, capture full payloads in a separate archival store before the claim-check reference goes stale — the event log alone is no longer the system of record once you adopt this pattern.
5. **Version the payload schema independently.** Envelope schema and payload schema evolve on different cadences. Tag the envelope with a payload schema version so consumers can pick the right deserializer after fetching.

## Failure Modes and Gotchas

1. **Dual-write consistency.** Producer writes blob then message; a crash between the two orphans a blob (harmless) — but the reverse order (message then blob) produces dangling references consumers will hit. Always write the payload first, and prefer idempotent, hash-keyed writes so producer retries are safe.
2. **Storage outage becomes messaging outage.** The pattern couples the bus to object storage availability. Consumers should degrade gracefully (queue the fetch, process envelope-only mode where the business allows it) rather than crash-looping on storage errors.
3. **Cost inversion at small sizes.** Below roughly 10–50 KB the extra round trip, per-request storage cost, and operational complexity usually exceed the savings. Apply claim-check selectively — a size threshold at the producer (publish inline under N bytes, claim-check above it) is the standard hybrid.
4. **Security review of references.** A leaked envelope must not grant access to sensitive payloads. If blobs hold PII, pre-signed URLs need short TTLs, and direct-key access needs per-consumer scoping — a single shared bucket readable by every subscriber recreates the trust-boundary problem the service layer was supposed to solve.
5. **Observability gap.** End-to-end latency now spans broker plus storage fetch, and dashboards that only watch broker lag will lie about consumer health. Emit metrics on fetch duration, fetch errors, and payload sizes to see the true processing curve.

## Related Patterns

1. **Event-carried state transfer.** Its inverse philosophy: instead of shipping big payloads with every event, replicate the needed state to consumers so events stay tiny. The two compose — transfer the summary fields, claim-check the full document.
2. **Outbox pattern.** The transactional outbox fixes the dual-write problem for database-plus-broker; claim-check needs the same discipline for storage-plus-broker. In practice the outbox row can carry the blob key so both writes coordinate through the database.
3. **Content-based deduplication.** Hash-addressed blob keys make producer retries idempotent and enable downstream caching, borrowing directly from content-addressable storage design.
4. **Aggregator / batch consumers.** Consumers that accumulate many events before acting can prefetch payloads concurrently — the claim-check reference is a natural unit for parallel fetching with bounded concurrency.
