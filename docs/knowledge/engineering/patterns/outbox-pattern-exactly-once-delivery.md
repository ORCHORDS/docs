# Outbox Pattern Exactly Once Delivery

## Scope

This article covers the transactional outbox pattern and the exactly-once question that surrounds it: guaranteeing that a state change and its outgoing message are both recorded or neither is, then reasoning precisely about what delivery guarantee the relay can offer downstream. Scope covers the atomicity mechanism, relay implementations (polling publisher versus change data capture), end-to-end delivery semantics (at-most-once, at-least-once, effectively-once), and the consumer-side machinery that converts at-least-once into effectively-once processing. It excludes saga orchestration and domain event modeling, which have their own articles.

## Workflow or implementation guidance

Understand first what the pattern does and does not claim. The outbox makes capture atomic: the business mutation and the event insert commit in one database transaction. It cannot make delivery atomic — a message broker acknowledgment cannot join a local database transaction — so the honest ceiling is at-least-once delivery plus idempotent, deduplicating consumers, which together yield effectively-once side effects. Systems that claim true exactly-once end to end are claiming either single-system transactionality or a narrower definition; treat any such claim as a scope question to be answered in writing before it becomes an outage debate.

Implement the write side as a strict transaction:

```sql
BEGIN;
UPDATE accounts SET balance = balance - ? WHERE id = ? AND balance >= ?;
INSERT INTO outbox (event_id, aggregate_id, type, payload, created_at)
VALUES (?, ?, 'PaymentDebited', ?, now());
COMMIT;
```

Then choose a relay. A polling publisher claims unpublished rows with a lease (`UPDATE ... SET locked_by = ?, locked_until = ? WHERE published = false AND (locked_until IS NULL OR locked_until < now())`), publishes, marks published. It is simple and portable, at the cost of polling latency and scan load. Change data capture reads the database's write-ahead log, transforming outbox inserts into broker messages with lower latency and no polling pressure, at the cost of additional infrastructure with its own operational profile. Either way, the relay must be crash-safe at every point: crash before publish means the row stays claimable; crash after publish but before marking means redelivery, which is expected and must be harmless.

The consumer side is where exactly-once is actually manufactured. Give every message a stable unique id (the outbox event id), and process each id exactly once per destination by recording processed ids transactionally with the side effect:

```ts
async function handleMessage(msg: Message, dest: SideEffectStore): Promise<void> {
  await dest.transaction(async (tx) => {
    const already = await tx.insertIfAbsent('processed_events', { event_id: msg.eventId });
    if (!already) return;                  // duplicate — side effect already applied
    await tx.applySideEffect(msg.payload); // same transaction as the marker
  });
}
```

The marker and the side effect must share one transaction; a marker written in a separate step converts at-least-once into at-most-once by suppressing redelivery of work that never happened. Finally, respect ordering where the domain requires it: partition relay and consumption by aggregate id so per-entity causality holds, and design consumers to tolerate cross-entity interleaving.

## Controls

Instrument the outbox as a contract with three alarms: depth (undelivered count), age of oldest unpublished row, and duplicate-delivery rate observed downstream. Depth growth is silent business failure — state changed, world not told — so it pages, not just charts. Enforce the atomic write mechanically with a shared repository method performing mutation plus insert in one transaction, and a review rule that no code path mutates aggregate tables outside it. For the relay, require lease-expiry handling with a bounded claim window and a metric on lease churn, since a too-short lease causes thrashing double-publish and a too-long one delays recovery after crashes. On the consumer side, require the processed-marker table to share the side effect's transaction — verified by a code-review checklist item, because this one placement decision is the difference between effectively-once and silently-lost work. Bound the marker table with retention aligned to the maximum plausible redelivery window plus margin, and document the assumption. Version the event envelope so relay upgrades cannot strand in-flight messages.

## Validation evidence

Atomicity proof: inject a failure between the outbox insert and commit, and a second between commit and relay pickup, and assert respectively that neither mutation nor event exists, and that both do with the event subsequently delivered. This directly verifies the core invariant. Duplicate-delivery test: configure the relay to double-send a sampled window of events and assert the consumer's side effects occur exactly once per event id — the test exercises the marker path deliberately, since production will exercise it accidentally. Crash matrix: kill the relay at each of the four points around publish-and-mark, restart, and assert the outcome is always delivery at least once and side effects exactly once. Ordering test: burst events for one aggregate through the relay and assert consumer-visible order per aggregate. Marker-retention test: replay a message older than the retention window and assert the documented behavior (reprocessing or rejection) occurs rather than an undefined state. Production evidence: duplicate-delivery rate and end-to-end latency from outbox insert to consumer side effect, charted over time — a duplicate rate above zero with zero duplicate side effects is the system working as designed, and it should be visible so nobody mistakes the design's at-least-once nature for a defect.

## Failure modes and correction

The canonical failure is the dual-write reintroduced by performance pressure: an event published directly to the broker after commit for latency reasons, where a crash between commit and publish loses the message forever. Correct by making direct broker access impossible from application code and reconciling broker counts against outbox rows. The second is the separated marker: consumer writes the dedup marker in its own transaction before the side effect, a crash lands between them, redelivery is suppressed, and the side effect never happens — at-most-once by accident, the worst possible failure because it is silent. Correct by co-locating marker and side effect in one transaction, verified by the crash-matrix test. The third is relay stall: the polling loop dies or CDC falls behind and events accumulate with no page because request-path monitoring is green. Correct with the depth and age alarms. A fourth is lease thrash: multiple relay instances with short leases repeatedly steal each other's claims, double-publishing at a rate that turns duplicate handling from occasional to constant. Correct by tuning lease duration against observed publish latency and monitoring lease-churn metrics. A fifth is marker table overflow: the dedup table grows unbounded, queries slow, and someone truncates it during an incident — reprocessing months of events. Correct with planned retention and a reprocessing runbook that makes the consequence of truncation explicit before anyone does it under pressure.

## Limitations

The pattern's guarantee is scoped to capture-atomicity plus relay reliability; it cannot bound delivery delay during relay failure, so any downstream expectation of freshness needs its own monitoring and its own degraded-mode story. Effectively-once processing holds only for side effects that live in a store capable of the marker-plus-effect transaction — effects on systems outside that transactional reach (emails sent, third-party API calls) remain genuinely at-least-once and need business-level tolerance or compensations. Ordering is per-aggregate at best; global ordering requires a single-partition relay that becomes a throughput bottleneck, and choosing that trade is domain-specific work the pattern does not do for you. The polling relay adds a latency floor and a standing load on the transactional store; the CDC relay removes both but adds log-reading infrastructure whose failure modes (schema changes, log retention gaps, offset loss) are unfamiliar to most application teams. Idempotent consumer design is a permanent tax on every consumer ever written against these events, and one non-idempotent consumer reintroduces duplicate side effects despite everything upstream working correctly.

## Canonical sources

- Debezium documentation — Debezium JDBC `io.debezium.outbox.event.router` (CDC-based outbox relay): https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html
- Chris Richardson — microservices.io, Transactional Outbox pattern (atomic capture with at-least-once relay semantics): https://microservices.io/patterns/data/transactional-outbox.html
- AWS Builders' Library — Timeouts, retries, and backoff with jitter (idempotency and retry interplay in at-least-once systems): https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/
- Cloudflare Queues documentation (at-least-once delivery and consumer retry semantics): https://developers.cloudflare.com/queues/
