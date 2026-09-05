# Kafka Cluster Version Bump Playbook

## Purpose

Drive an Apache Kafka cluster (or client library) to a new minor version without data loss, consumer-group rebalance storms, or unrecoverable transaction state. The playbook covers both ZK-mode and KRaft clusters, and both broker-bump and client-bump paths.

## Audience

Kafka operators, SRE on-call, platform-team engineers responsible for the event-streaming reference architecture.

## Pre-conditions

1. The target version is on the supported matrix in `KAFKA_KIP_VERSION_GOVERNANCE.md` and is no more than one minor beyond the current production version.
2. A staging cluster mirrors production topology (broker count, partition count, replication factor, ISR topology).
3. Synthetic load generators (`kafka-producer-perf-test`, `kafka-consumer-perf-test`) are configured for representative workload mix.
4. `inter.broker.protocol.version` and `log.message.format.version` are pinned to the current minor.
5. The PR for the bump is reviewed and merged before the change window opens.

## Procedure

### 1. Confirm supported KIPs

For the target Kafka release, walk the matrix in `KAFKA_KIP_VERSION_GOVERNANCE.md` and identify every Notable KIP. Document each in the change ticket with one of: "not in scope", "in scope, mitigated by config", "in scope, requires code change". Every "requires code change" entry must have an associated PR linked.

### 2. Validate in staging

1. Roll staging brokers one at a time. Each restart: monitor `kafka.controller:type=ControllerStats`, `kafka.server:type=BrokerTopicMetrics`, under-replicated partition count.
2. Run synthetic load: 50% producer-only, 30% consumer, 20% transactional (idempotent + EOS). Verify zero `OutOfOrderSequence`, zero `InvalidProducerEpoch`, zero consumer rebalances in 30 minutes.
3. Trigger KRaft metadata version bump if applicable (`kafka-storage.sh format -t <clusterId> -c <config>`).
4. Confirm client library compatibility for every producer/consumer in the dependency graph.

### 3. Production roll

1. Announce a 4-hour change window. On-call escalation contacts posted in the incident channel.
2. For ZK-mode clusters: bump `inter.broker.protocol.version` first, restart brokers one at a time with 10-minute separation.
3. For KRaft clusters: stage the new binary alongside the old; restart the controller quorum first, then the broker quorum.
4. After every restart: verify ISR shrinks to full within 60 seconds; verify under-replicated partitions = 0.
5. After all broker restarts: run `kafka-broker-api-versions.sh --bootstrap-server <host>` and confirm the protocol-feature matrix matches expectations.

### 4. Client migration

1. Schedule a 7-day dual-write window during which both old and new client libraries are running side-by-side.
2. New clients produce to a shadow topic; verify message-level parity against the legacy topic.
3. Cut consumers over one consumer group at a time. Verify the consumer's last-committed offset matches the shadow topic's earliest offset.

### 5. Validation

- Producer p99 latency ≤ baseline + 10%
- Consumer lag (per partition) ≤ baseline + 5%
- Transaction abort rate ≤ 0.01% under steady state
- KRaft controller log lag = 0

## Rollback

| Symptom | Rollback action |
|---|---|
| Broker fails to join quorum | revert broker binary; restart |
| Consumer rebalance storm | revert client to last-good version; force consumer group reset |
| Transaction abort rate > 1% | revert broker version; abort in-flight transactions |
| KRaft metadata corruption | stop broker, restore from snapshot, restart on prior version |
| Inter-broker protocol mismatch | set `inter.broker.protocol.version` back to prior minor |

Rollback decisions must be made within 30 minutes of the first symptom. Every rollback triggers `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` within 5 business days.

## References

- `KAFKA_KIP_VERSION_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- Apache Kafka upgrade guide: `https://kafka.apache.org/documentation/#upgrade`
- KRaft upgrade guide: `https://kafka.apache.org/documentation/#kraft_upgrading`
