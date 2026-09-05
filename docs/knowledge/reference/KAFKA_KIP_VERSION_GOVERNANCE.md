---
title: Apache Kafka Version Governance (KIP-driven protocol)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Apache Kafka KIP repository (https://kafka.apache.org/documentation/#design_apis); KIP-500 (KRaft), KIP-98 (Exactly-once / EOS), KIP-848 (Next-generation consumer group protocol), KIP-405 (Kraft bootstrap); https://kafka.apache.org/protocol
---

# Apache Kafka Version Governance (KIP-driven protocol)

## Scope

This card governs how `orchords-docs` evaluates and adopts new Apache Kafka releases and the Kafka Improvement Proposals (KIPs) that drive wire protocol, API, and cluster-membership changes. It is the reference input for the Kafka cluster reference architecture, the event-streaming platform reference, and any change-managed Kafka broker configuration committed to `orchords-docs` infrastructure.

## Why this card exists

Kafka ships a continuously evolving protocol: each Kafka release bundles KIPs that can change wire framing, default consumer-group semantics, replication guarantees, controller consensus, and security defaults. A KB card binding "Kafka version X" without enumerating the governing KIPs produces a configuration that quietly drifts from what production brokers expect.

## Protocol version matrix

| Kafka release | First KIP gating the release | Notable KIPs landing in this line |
|---|---|---|
| 0.9.0.0 | n/a | first security release, JAAS-based SASL |
| 0.11.0.0 | KIP-98 | idempotent producer, exactly-once semantics, message format v2 |
| 2.5.0 | KIP-500 prep | ZK-less mode (KRaft) preview |
| 2.8.0 | KIP-500 | KRaft early access (development mode) |
| 3.3.0 | KIP-848 | new consumer group protocol (beta) |
| 3.5.0 | KIP-848, KIP-405 | KRaft production-ready, consumer group KIP-848 alpha |
| 3.7.0 | KIP-848, KIP-996 | tiered storage production, KIP-848 ready-to-use |
| 3.8.0 | KIP-848 | consumer group protocol v2 default opt-in |

References: `https://kafka.apache.org/40/protocol.html`, `https://kafka.apache.org/documentation/#kraft`.

## KIP taxonomy

KIPs that change runtime behavior fall into four buckets for governance purposes:

1. **Wire protocol KIPs** — modify request/response framing, schema-id encoding (KIP-482 message format v2), record batch format. Migration must be staged: rolling restart on mixed-version brokers; never allow producer client newer than broker version it sends to.
2. **API KIPs** — AdminClient, Producer, Consumer, Streams. Adopt only after verifying all client libraries in the dependency graph are at the new minor minimum.
3. **Consensus / cluster membership KIPs** — KIP-500 (KRaft), KIP-405 (controller bootstrap), KIP-857 (controller-side metadata propagation). Migrating ZK to KRaft is a non-rolling change in spirit — run a parallel cluster, dual-write, cut over.
4. **Consumer group KIPs** — KIP-848 (next-gen consumer group protocol). Defaults flip from KIP-848 classic to KIP-848 next-gen by version pin; producers of consumer-client version mismatches see `REBALANCE_IN_PROGRESS` storms.

## Version support policy

- **Adoption window**: support the latest 3 Kafka minor releases at all times (N, N-1, N-2). Defer new-version intake until the first patch of N has shipped and no P1 CVEs remain unpatched in N-2.
- **Inter-broker protocol**: pin via `inter.broker.protocol.version` (ZK-mode clusters) or via rolling upgrade metadata, never advance more than one minor version per rolling restart cycle.
- **Client version floor**: producers/consumers must be within the supported release window of the broker; older clients are blocked at the broker by default (`unclean.leader.election.enable=false`, `min.insync.replicas` ≥ 2).
- **KIP-848 transition**: production clusters roll KIP-848 next-gen over a 30-day shadow window with the classic protocol enabled in parallel, and cut over only when `consumer.protocol.rebalance.lag.p99` and `__consumer_offsets` write-amplification both flatten.

## Mandatory operator pre-flight (before any version bump)

1. Confirm the new minor is on the supported list above; if not, document the exception in the change ticket.
2. Read every "Notable KIPs landing in this line" entry in the matrix above against the running cluster's config map.
3. Run `kafka-broker-api-versions.sh --bootstrap-server <host>` against a staging cluster and diff against production to detect protocol-feature drift.
4. Validate EOS pipelines (KIP-98) against idempotency keys in `transaction.state.log.replication.factor=3` with `transaction.state.log.min.isr=2`.
5. For KRaft: confirm controller quorum `kraft.metadata.version` matches the broker binary version; do not run a controller metadata version older than the broker version.

## Security-relevant KIPs

- **KIP-152 and prior SASL series** — SASL/OAUTHBEARER (KIP-285), SASL/SCRAM (KIP-84). Pin to PLAINTEXT-disabled broker config (`listeners`, `advertised.listeners`, `inter.broker.listener.name`).
- **KIP-103 / KIP-219** — TLS 1.2+ minimum, prefer TLS 1.3. Disable cipher suites listed in `ssl.enabled.protocols` if any client claims support but fails negotiation.
- **KIP-554** — ZooKeeper digest authentication in ZK-mode clusters. Must pair with `zookeeper.set.acl=true`.
- **KIP-848** — consumer group protocol v2 enables cooperative-sticky assignment by default; audit partition.assignment.strategy values during migration to avoid static-assignment regressions.

## Observability and SLO gates

- Producer p99 latency, request-rate, batch-size histograms via the JMX exporter.
- Consumer rebalance rate (`kafka.consumer:type=consumer-fetch-manager-metrics,client-id=*`) — alarm when rebalances/min > 0.1 sustained over 10 minutes for any consumer group.
- Under-replicated partitions (`kafka.server:type=ReplicaManager,name=UnderReplicatedPartitions`) — must equal 0 in steady state.
- KRaft controller log lag (`kafka.controller:type=ControllerStats,name=ActiveControllerCount`).

## Deprecation and sunset tracking

KIPs that the project treats as "sunset" must remain commented in the cluster config (not deleted) for at least 90 days after the canonical version-bump documentation is updated. This makes rollback possible without re-reading the original config.

## Sources

- Apache Kafka protocol documentation: `https://kafka.apache.org/protocol.html`
- KIP index: `https://cwiki.apache.org/confluence/display/KAFKA/Kafka+Improvement+Proposals`
- KRaft documentation: `https://kafka.apache.org/documentation/#kraft`
- Exactly-once semantics: KIP-98 (`https://cwiki.apache.org/confluence/display/KAFKA/KIP-98+-+Exactly+Once+Delivery+and+Transactional+Messaging`)
- Next-gen consumer group: KIP-848 (`https://cwiki.apache.org/confluence/display/KAFKA/KIP-848%3A+The+Next+Generation+of+the+Consumer+Group+Protocol`)
