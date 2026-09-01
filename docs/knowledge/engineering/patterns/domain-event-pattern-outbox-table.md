# Domain Event Pattern Outbox Table

## Scope

This article covers domain events published through a transactional outbox table: business-relevant state changes recorded as events inside the same transaction that mutates state, then relayed asynchronously to a broker or queue by a separate publisher. Scope covers what qualifies as a domain event versus an integration event, the outbox write discipline, relay mechanics and ordering, at-least-once consumption consequences, and event envelope design. It excludes the outbox-as-exactly-once-delivery question and full event sourcing, both of which have their own articles.

## Workflow or implementation guidance

Start by selecting events from the language of the domain, not from the mechanics of the code: `OrderPlaced`, `ShipmentDelayed`, `CreditLimitExceeded` — things a business stakeholder recognizes and cares about. Implementation occurrences are not domain events: `RowUpdated`, `TransactionCommitted`, `CacheInvalidated` are integration or technical events and belong on a different channel with different contracts. Each domain event should represent a fact that became true, be named in past tense, and carry the identifiers and values a consumer needs without a callback.

Write events transactionally with the state change:

```sql
BEGIN;
UPDATE orders SET status = 'confirmed' WHERE id = ? AND status = 'placed';
INSERT INTO outbox (event_id, aggregate_id, type, payload, headers, occurred_at)
VALUES (?, ?, 'OrderConfirmed', ?, ?, now());
COMMIT;
```

This single transaction is the entire correctness argument: either the state changed and the event exists, or neither did. Anything that weakens it — publishing after commit from application memory, writing the event in a second transaction, capturing events in an in-memory list that a crash can drop — reintroduces the lost-update and phantom-event problems the pattern exists to eliminate.

Relay mechanics come next. A publisher polls or subscribes to the outbox, claims unpublished rows with a lease (so multiple relay instances do not double-publish), sends to the broker, and marks published — the mark is best-effort and idempotent consumers downstream make at-most-once marking safe. Two disciplines matter here. First, publish in aggregate order: relay by `aggregate_id` partition so consumers observe per-aggregate causality, while accepting global interleaving across aggregates. Second, include enough envelope metadata for consumers to function: event id, type and schema version, aggregate id and version, occurred-at, and correlation ids from the initiating command. Consumers need the version to detect gaps and the event id to deduplicate.

Keep payloads self-contained but minimal: identifiers and business-relevant values, not whole internal rows. A consumer that must call back for every field couples the event contract to your read availability and turns every event into a distributed query.

## Controls

Treat the outbox as critical data with its own controls. Monitor outbox depth and age as first-class operational metrics with alarms — a growing queue means events are being generated but not delivered, which is silent business failure (customers not notified, projections drifting) invisible to request-path monitoring. Enforce the transactional write mechanically: a shared repository method that performs mutation plus outbox insert in one transaction, with a review rule that no code path mutates aggregate tables outside it. Require a retention and archival policy for published rows (mark-and-purge or move to cold storage), because an unpurged outbox slows polling and inflates storage indefinitely. Version event schemas additively with a documented policy, and register every event type with its owning team in a catalog — a discovered-in-production event type with no owner is how contracts break. For relay reliability, require lease-expiry handling so a crashed relay's claimed rows return to the pool, and alert on rows older than the delivery SLO.

## Validation evidence

The decisive test is the atomicity proof: begin a transaction, mutate, insert the outbox row, then force a rollback (crash the connection or inject a failure) and assert neither the mutation nor the outbox row exists; then let it commit and assert both exist. This directly verifies the invariant everything else depends on. Duplicate-delivery test: configure the relay to double-send a sampled event and assert downstream consumers deduplicate on event id with no duplicate side effects — because at-least-once delivery makes this path certain in production. Ordering test: publish a burst of events for one aggregate and assert consumers observe them in version order under partitioned relay. Crash-recovery test: kill the relay mid-batch and assert a restarted relay reclaims expired leases and completes delivery without duplicates at the broker (or, where duplicates are possible, that consumers handle them). Production evidence: outbox age distribution against delivery SLO, plus a periodic end-to-end trace — command to outbox row to broker message to consumer side effect — sampled from live traffic, confirming the whole chain still functions rather than assuming it.

## Failure modes and correction

The most damaging failure is the bypassed outbox: a hot path publishes directly to the broker after commit for latency reasons, and a crash between commit and publish loses the event forever — invisible, unmonitored, unreportable. Correct by making direct broker access impossible from application code and by reconciling broker topic counts against outbox publication counts. The second is relay stall without alarm: the relay dies, outbox depth grows for hours, and the first symptom is a business complaint about missing notifications. Correct with depth and age alarms wired to the on-call rotation, not to a dashboard someone checks. The third is ordering corruption under naive relay: a publisher claims rows without aggregate partitioning and delivers an aggregate's events out of order, producing nonsensical consumer state (order cancelled before placed). Correct by partitioning relay claims and delivery on aggregate id. A fourth is unbounded growth: published rows are never purged, polling scans degrade, and the fix becomes a risky mass delete under pressure. Correct with an automated purge job and a tested archival path. A fifth is the anemic event: payloads carry only ids, consumers call back for every field, and each event becomes a distributed query against the producer's read path. Correct at contract design time with the self-contained payload discipline.

## Limitations

The outbox guarantees atomic capture and at-least-once relay — nothing more. Delivery remains asynchronous with unbounded delay under relay failure, so consumers must tolerate staleness, and any UI requirement for immediate reaction needs a synchronous path the pattern deliberately does not provide. At-least-once means every consumer carries deduplication burden forever; the pattern pushes exactly-once reasoning to the consumer side, where it is harder to verify. The pattern presumes a transactional store capable of committing mutation plus event insert together — systems whose primary store lacks transactions, or whose mutations span stores, cannot use it without first consolidating the transactional boundary. Polling-based relays add latency and load-floor cost; log-based relays (such as change data capture over the outbox) reduce both but introduce new infrastructure with its own operational profile. Event schema evolution is constrained by consumer diversity: you cannot fix a bad event contract, only version alongside it, so early design errors persist for the retention lifetime of every consumer's interest.

## Canonical sources

- Fowler — Domain Event: https://martinfowler.com/eaaDev/DomainEvent.html
- Debezium documentation — Debezium JDBC `io.debezium.outbox.event.router` (outbox table event routing): https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html
- Chris Richardson — microservices.io, Transactional Outbox pattern: https://microservices.io/patterns/data/transactional-outbox.html
- Microsoft Azure Architecture Center — Event Sourcing pattern (the state-reconstruction sibling of recorded events): https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing
