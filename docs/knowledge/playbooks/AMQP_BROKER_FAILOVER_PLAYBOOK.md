# AMQP Broker Failover and Client Reconnect Playbook

## Purpose

Drive predictable client behavior when an AMQP broker (RabbitMQ, ActiveMQ Artemis, Azure Service Bus) fails over or migrates. The playbook covers client-side reconnect tuning, server-side cluster topology choices, and the operational telemetry that confirms the failover is "clean".

## Audience

AMQP application owners, SRE on-call, message-broker operators.

## Pre-conditions

1. Client uses `amqp091-go` (AMQP 0-9-1) or `qpid-jms-client` / `AmqpNetLite` / `qpid-proton` (AMQP 1.0).
2. Broker is configured for quorum + replica topology with at least 3 nodes.
3. Publisher confirms are enabled on every channel.
4. Idempotent consumer (manual ack with `multiple=false`, deduplication key in the payload).
5. The reference card for the protocol is current: `AMQP_0_9_1_VERSION_GOVERNANCE.md` or `AMQP_1_0_VERSION_GOVERNANCE.md`.

## Procedure

### 1. Pre-failover: confirm the failover mode

| Failover mode | When to use | Client behavior |
|---|---|---|
| Broker-initiated (`queue.master-locator`) | Cluster of identical brokers, same zone | Client reconnects to advertised node |
| Client-initiated (DNS or VIP) | Active/passive broker pair | Client resolves to the new broker on next attempt |
| Server-side fencing (quorum) | Raft-consensus brokers (quorum queues) | Failover is broker-internal; client sees only the connection-drop |

The mode must be documented in the reference architecture card.

### 2. Detect the failover

Client observability must emit on every connection drop:

- `amqp.connection.attempts` (counter)
- `amqp.connection.failed` (counter)
- `amqp.connection.last_error` (gauge: textual)
- `amqp.consumer.rebalance.lag_ms` (gauge)

Trigger the playbook when `amqp.connection.failed` rate > 0.05/sec sustained over 5 minutes, or when a single broker node restart is announced.

### 3. Client reconnect tuning

| Setting (AMQP 0-9-1) | Default | Recommended |
|---|---|---|
| `heartbeat` | 60s | `min(60s, application_health_timeout / 2)` |
| `connection_timeout` | 30s | 5s for fail-fast, 30s for stability |
| `reconnect_interval` | 5s | exponential backoff: 1s → 30s |
| `max_reconnects` | ∞ (until context cancel) | n/a (never give up) |
| `channel_prefetch` (consumer) | 0 (unbounded) | 10–250 based on workload |

| Setting (AMQP 1.0) | Default | Recommended |
|---|---|---|
| `idle-time-out` | server-supplied | echo server value, refuse 0 |
| `incoming-window` | 65 535 | ≥ 4 × `link-credit` × max-message-size |
| `outgoing-window` | 65 535 | 65 535 (default is fine) |
| `link-credit` | 1 (initial) | 30 / 250 / 1024 per workload tier |
| reconnect-on-link-detach | implicit | explicit: re-`Attach` after broker `link-detach` |

### 4. Drain or fail-fast

For stateful consumers (transactional pipelines):

1. On connection drop, the client must immediately stop the consumer (`basic.cancel` or `link.detach`) before reconnect.
2. After reconnect, the consumer must re-declare any stateful resources (durable subscriptions, exclusive queues, transactional state).
3. Any in-flight unacknowledged messages are returned to the broker on drop; clients must NOT re-deliver until they have been returned (avoid double-delivery).

For stateless consumers (fire-and-forget telemetry):

1. Reconnect is automatic; client does not need to drain.
2. Drops are visible as `amqp.consumer.messages.lost` counter increments.

### 5. Validate the failover

- Reconnect time ≤ 5 × heartbeat (i.e., heartbeat=10s → reconnect ≤ 50s).
- In-flight message loss = 0 (publisher confirms must be re-acquired post-reconnect).
- Quorum queue leader election ≤ 30s.
- Consumer lag returns to pre-failover within 5 minutes.

## Rollback

Rollback of a failover is not possible in the strict sense — once a quorum leader has moved, you cannot move it back without restarting the broker. Instead:

1. If the failover was triggered by a misconfiguration, fix the configuration on the surviving nodes first.
2. Once fixed, perform a controlled restart of the cluster during the next change window.

## References

- `AMQP_0_9_1_VERSION_GOVERNANCE.md`
- `AMQP_1_0_VERSION_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- RabbitMQ clustering: `https://www.rabbitmq.com/docs/clustering`
- RabbitMQ quorum queues: `https://www.rabbitmq.com/docs/quorum-queues`
- AMQP 1.0 link recovery: `https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-messaging-v1.0-os.html`
