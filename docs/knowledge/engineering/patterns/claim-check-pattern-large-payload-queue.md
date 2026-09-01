# Claim Check Pattern Large Payload Queue

## Scope

This article covers the Claim Check pattern — also called store-and-reference or reference-based messaging — for routing payloads too large for a message queue through a side store, sending only a reference through the channel. Scope covers the decision boundary and sizing rules for when to claim-check rather than inline a payload, single-consumer and fan-out consumption, retention and lifecycle of the referenced object, and idempotent handling when the reference is redelivered. It assumes a durable object store alongside the queue; it does not cover the queue's own delivery semantics, nor streaming transport of large bodies where no queue is involved.

## Workflow or implementation guidance

First, establish the size threshold as a policy, not a per-developer judgment call. Measure the message size before serialization, and claim-check above a fraction of the queue's hard limit — a common rule is one quarter to one half — so that metadata, headers, and future field growth cannot push borderline messages over the edge at runtime. Encode the threshold in one shared helper that every producer route uses; a threshold applied inconsistently across producers is the primary source of "message too large" incidents.

Second, design the reference as a first-class contract rather than a bare key. A robust claim contains the storage key, the payload's content type and byte length, an optional checksum, and a schema version for the claim itself:

```ts
interface Claim {
  kind: 'claim';
  storageKey: string;
  contentType: string;
  byteLength: number;
  sha256?: string;
  claimVersion: 1;
}
```

Third, sequence the producer as store-then-send with an explicit reconciliation state. The two operations are not atomic: the store can succeed while the send fails, leaving an orphaned object, or — worse in some systems — a send could reference an object that failed to store. Write the object first, record a pending-claim row in a transactional store, then send, then mark sent. A periodic sweeper deletes pending rows whose send never confirmed. Fourth, on the consumer side, treat a missing object as a distinct failure class: a `null` on fetch means the claim is unrecoverable, so retrying is pointless — dead-letter it with the claim's metadata rather than burning retry attempts against a key that will never resolve.

Checksum verification on read is cheap and catches the silent-corruption class of bug: verify the payload hash against the claim before processing, and reject on mismatch into a quarantine path with both hashes recorded. For fan-out, write one object and send N claims referencing it; delete only after all consumers acknowledge, tracked with a per-claim consumer ledger. Choose storage keys with a time-sortable prefix plus a random suffix — sequential keys create hot partitions in object stores that spread load by key hash.

## Controls

Enforce the size policy mechanically: a shared `sendWithClaimCheck` helper that internally measures, decides, and routes — plus a code-review check that no route calls the raw queue send with a caller-supplied body. Require TTL or lifecycle rules on the claim store bucket, with an explicit exception process for claims that must outlive the default window; unbounded claim stores are a quiet cost and blast-radius problem. Make the consumer's missing-object path observable and alarmed: a rising `claim_not_found` rate means either lifecycle rules are deleting too early, producers are sending before storing completes, or keys are malformed — three very different fixes, distinguishable only if the metric exists. Track end-to-end claim age from store time to process time, because the pattern adds a store hop on both sides and its latency contribution must be visible. For multi-consumer claims, require the acknowledgment ledger to be the delete authority — no consumer deletes the object it processed.

## Validation evidence

Validate the boundary and the lifecycle. Boundary tests: for payloads straddling the threshold, assert that inline and claim-checked paths both complete, that the claim's byte length matches the stored object's size, and that the checksum verifies — run these with real queue and store bindings in a staging environment, since size accounting differs subtly between local serialization and the real serializer. Reconciliation test: force a failure between store and send, advance the sweeper, and assert the orphaned object is deleted and the pending row cleared. Redelivery test: process the same claim twice and assert the outcome is identical (idempotent) and no duplicate side effects occur, since at-least-once delivery makes this path certain in production, not hypothetical. Fan-out test: with three registered consumers, acknowledge two, force a redelivery to the third, and assert the object still resolves — premature deletion after partial acknowledgment is the fan-out failure mode this test exists to catch. Load evidence: a run at several times expected peak payload volume, confirming queue depth stays flat while the claim store absorbs the bytes and the size distribution of enqueued messages never approaches the hard limit.

## Failure modes and correction

The most frequent production failure is threshold bypass — a new producer inlines payloads that exceed the limit and the queue rejects them at runtime. Correct by making the raw send path inaccessible outside the helper, and by alerting on the queue's own size-rejection errors as a backstop. The second is premature deletion in fan-out: one consumer's acknowledgment triggers deletion while a slower consumer retries, gets `null`, and dead-letters work that was perfectly valid. Correct with the consumer ledger and delete-on-all-ack rule described above. The third is orphan accumulation on the store side from failed sends, which inflates cost and, worse, can mask a real bug when disk pressure forces premature lifecycle expiry. Correct with the pending-claim reconciliation sweeper and an orphan-count metric. A fourth is unversioned claim schemas: a field added to the claim breaks old in-flight messages after deploy; correct by versioning the claim envelope and dispatching on `claimVersion`. A fifth is hot-key partitioning from sequential keys; correct with randomized suffixes once the symptom — latency spikes on a narrow key range — appears in store-side metrics.

## Limitations

The pattern trades a byte-size problem for a distributed-consistency choreography: store and send cannot be made atomic without a transactional outbox, so producers carry reconciliation complexity forever. It adds two hops of latency per message (store, then fetch) and one more component whose availability now gates message processing. Small payloads claim-checked indiscriminately waste both hops — the threshold exists because the crossover is real. Consumer-side memory is bounded only if the consumer streams the object rather than buffering it whole; a "claim check" that loads a hundred-megabyte object into memory to read one field has moved the problem, not solved it. Object stores with eventual visibility on write can return `null` for a just-written claim under extreme write rates, forcing producers to add delay or retry logic. Finally, retention policy becomes a data-governance decision — payloads that outlive their claims leak data, and claims that outlive their payloads break redelivery — so the lifecycle rules need an owner, not a default.

## Canonical sources

- Hohpe and Woolf — Enterprise Integration Patterns, Addison-Wesley, 2004 (Claim Check / Store in Library): https://www.enterpriseintegrationpatterns.com/patterns/messaging/StoreInLibrary.html
- Microsoft Azure Architecture Center — Claim Check pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/claim-check
- Microsoft Azure Architecture Center — Priority Queue pattern (message-size and queue-depth trade-offs): https://learn.microsoft.com/en-us/azure/architecture/patterns/priority-queue
- Cloudflare R2 Workers API reference (object storage for claim payloads): https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
