# Pub Sub Pattern Topic Filter Semantics

## Scope

This article covers publish-subscribe with emphasis on topic filter semantics: how subscribers select the subset of published messages they receive, the differences between topic hierarchies with wildcards, subject-or-header attribute filters, and tag-based routing, and the consequences each choice has for coupling, ordering, and delivery guarantees. Scope covers filter design as a contract, ordering and per-subscriber state, dead-lettering of unmatched or rejected messages, and schema discipline across a topic's subscriber population. It excludes request-reply messaging, queue-based point-to-point load balancing (competing consumers), and broker product comparisons except where semantics differ materially.

## Workflow or implementation guidance

Choose the filter model consciously, because it determines what subscribers can express and what the contract enforces. A topic hierarchy with wildcards (`orders/eu/created`, subscribed as `orders/+/created` or `orders/#`) gives positional, human-readable routing: adding a dimension means re-encoding the hierarchy, but routing is cheap and observable. Attribute or subject filters (`messages where region = 'eu' AND type = 'created'`) give expressive ad-hoc selection at the cost of a query language to version and debug. Tag-based fan-out assigns each message a set of tags and delivers to all subscriptions matching any or all — best when the same message legitimately serves multiple, overlapping audiences. The choice is not free to revisit: subscriber code, tooling, and operational habits form around it.

Design filters as versioned contracts. On hierarchical topics, agree on the dimension order and the meaning of each position before the second dimension exists, because retrofitting a hierarchy means every subscriber changes at once. Publish with a stable schema per leaf topic and version the payload envelope — subscribers filter on the topic but bind to the schema, and an unannounced field rename breaks a population you cannot see.

Delivery and ordering semantics must be stated per subscription, not assumed: most pub-sub systems offer at-least-once delivery with ordering preserved only within a partition or subscription session, so consumers deduplicate on message id and tolerate cross-entity interleaving. Handle non-matching explicitly:

```ts
export default {
  async queue(batch: MessageBatch<Envelope>, env: Env): Promise<void> {
    for (const m of batch.messages) {
      if (!matchesSubscription(m.body, env.SUBSCRIPTION_RULES)) {
        m.ack();                            // deliberately not ours — count it, don't retry it
        continue;
      }
      try { await handle(m.body); m.ack(); }
      catch { m.retry(); }                  // our failure — redeliver per at-least-once
      }
  },
};
```

Conflating "not matched" with "failed to process" poisons delivery metrics and burns retry budgets on messages that will never match. Finally, scope subscriptions narrowly enough that a subscriber's blast radius is bounded: a subscription on `#` (everything) is an outage amplifier waiting for one malformed schema, and a review should treat it as a finding.

## Controls

Register every topic, its schema, and its subscriber population in a catalog with owners; unregistered topics are undiagnosable during incidents because nobody can say who receives what. Enforce schema compatibility per topic with contract tests run by every subscriber against the publisher's fixtures — additive evolution only, with a documented breaking-change policy that requires a new topic rather than in-place mutation. Require each subscription to declare its expected volume, ordering needs, and idempotency posture in the catalog entry, so capacity and semantics are recorded rather than rediscovered under load. Control wildcard breadth: subscriptions on top-level wildcards need explicit justification, since they couple a consumer to every future message the publisher will ever emit. Monitor per-subscription delivery lag, ack rate, and unmatched count separately — aggregate topic metrics hide the one sick subscriber that eventually backs up the subscription. Dead-letter policy must exist per subscription with an owner and a reprocessing runbook, because a subscription whose poison messages accumulate without review is a data-loss incident in progress.

## Validation evidence

Routing evidence is the core: a fixture suite publishes a matrix of messages spanning every filter dimension (each region, each message type, boundary values) and asserts each registered subscription receives exactly the messages its rule implies — no more, no fewer. This matrix is the executable definition of the filter contract, and a rule change is a diff against it. Ordering evidence: publish bursts of related messages sharing a partition key and assert per-key ordering per subscription while tolerating cross-key interleaving, under production-shaped concurrency. Duplicate evidence: configure redelivery of a sampled window and assert subscribers deduplicate on message id with exactly-once side effects, verifying the at-least-once posture is real rather than assumed. Schema evidence: each subscriber runs the publisher's contract fixtures in CI, so a publisher-side breaking change fails subscriber builds rather than production. Load evidence: fan-out ratio (messages published versus delivered across subscriptions) measured at expected peak, since a topic with ten matching subscriptions multiplies broker load tenfold and that multiplication must appear in capacity plans, not in a postmortem. DLQ evidence: inject a poison message and verify it lands in the subscription's dead-letter target with its original metadata and that the alarm fires.

## Failure modes and correction

The most common failure is the over-broad subscription: a subscriber registers a top-level wildcard, a publisher adds an unexpected message type, and the subscriber's handler throws on an unrecognized schema — turning a routing convenience into a downstream outage. Correct by narrowing subscriptions to explicit patterns and requiring justification for wildcards, with the unmatched-handling path counting and acknowledging rather than retrying. The second is silent mismatch: a subscriber's filter is subtly wrong (wrong position in the hierarchy, wrong attribute name) and it simply receives nothing, with no error anywhere. Correct with the routing matrix test plus a canary message per subscription published on a schedule, whose receipt is asserted — a subscription that has not received its canary is misrouted or dead. A third is schema drift on a shared topic: one publisher team renames a field, half the subscribers break, and the catalog is stale enough that the blast radius is unknown. Correct with subscriber-side contract tests and a registry that gates topic changes on subscriber sign-off. A fourth is ordering assumption violation: a consumer assumes global order, the broker partitions for throughput, and state corrupts in ways that appear only under load. Correct by documenting per-key ordering as the guarantee and modeling consumers accordingly. A fifth is DLQ neglect: poison messages accumulate unowned, and the eventual cleanup decision is made without the context needed to reprocess safely. Correct with DLQ age alarms and a named owner per subscription.

## Limitations

Filter expressiveness is bounded by the broker model chosen at the start, and migrating filter models later means changing every publisher and subscriber simultaneously — the pattern's core flexibility ends at its routing language. Complex attribute filters push evaluation cost onto the broker or the subscriber's own code, and either way the filtering work grows with message volume regardless of how few messages ultimately match. At-least-once delivery and per-partition ordering are the practical ceiling for distributed brokers; consumers demanding stricter guarantees need transactional messaging or acknowledgment protocols layered on top, which pub-sub does not supply. Fan-out multiplies infrastructure load by subscriber count, so adding subscribers is a capacity decision as much as a code change, and backpressure from one slow subscriber can affect delivery to others depending on the broker's isolation model. Topic hierarchies encode an ontology that ages badly as the domain evolves — the dimension order that was obvious at design time becomes a constraint nobody can change cheaply. Finally, debugging delivery problems spans publisher, broker, filter, and subscriber, and without end-to-end tracing identifiers propagated through the envelope, reconstructing why a message did or did not arrive is manual archaeology.

## Canonical sources

- Hohpe and Woolf — Enterprise Integration Patterns, Addison-Wesley, 2004 (Publish-Subscribe Channel): https://www.enterpriseintegrationpatterns.com/patterns/messaging/PublishSubscribeChannel.html
- Microsoft Azure Architecture Center — Publisher/Subscriber pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/publisher-subscriber
- Cloudflare Pub/Sub documentation (topic and broker routing semantics at the edge): https://developers.cloudflare.com/pub-sub/
- Cloudflare Queues documentation (consumer delivery, retry, and dead-letter semantics): https://developers.cloudflare.com/queues/
