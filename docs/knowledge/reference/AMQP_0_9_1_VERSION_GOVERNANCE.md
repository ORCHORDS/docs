---
title: AMQP 0-9-1 Version Governance (RabbitMQ wire protocol baseline)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: AMQP 0-9-1 specification (OASIS, October 2008); AMQP 0-9-1 errata; RabbitMQ AMQP 0-9-1 reference (https://www.rabbitmq.com/amqp-0-9-1-reference.html); https://www.amqp.org/specification/0-9-1
---

# AMQP 0-9-1 Version Governance (RabbitMQ wire protocol baseline)

## Scope

This card governs the AMQP 0-9-1 wire protocol as deployed by RabbitMQ and as understood by AMQP 0-9-1 client libraries (`amqp091-go`, `pika`, `amqplib`, `RabbitMQ.Client`). It is the reference input for the message-broker reference architecture and for any orchestrator that speaks AMQP 0-9-1 against managed RabbitMQ brokers.

## Why this card exists

AMQP 0-9-1 is a frozen specification (last errata: 2008). Most operational pain comes from a mismatch between client-side assumptions (librabbitmq 0.9.x vs 0.10.x, Go client `streadway/amqp` vs `rabbitmq/amqp091-go`) and server-side extensions (`x-queue-type`, `x-message-ttl`, `x-dead-letter-exchange`, `x-priority`, `quorum` queue arguments). Treating AMQP 0-9-1 as "version-less" produces broker behavior that is hard to diagnose.

## Protocol version support matrix

| Client family | AMQP spec version | Compatible RabbitMQ broker versions |
|---|---|---|
| `amqp091-go` (formerly streadway/amqp) | 0-9-1 | 3.8.x, 3.9.x, 3.10.x, 3.11.x, 3.12.x, 3.13.x |
| `pika` (Python) | 0-9-1 | 3.8.x — 3.13.x |
| `amqplib` (Node.js) | 0-9-1 | 3.8.x — 3.13.x |
| `RabbitMQ.Client` (.NET) | 0-9-1 | 3.8.x — 3.13.x |
| `librabbitmq-c` | 0-9-1 | 3.8.x — 3.13.x |
| `qpid-proton` (AMQP 1.0 only) | 1.0 | n/a — use AMQP 1.0 governance card |

References: `https://www.rabbitmq.com/client-libraries/amqp-0-9-1-client-libraries.html`.

## Channel / class / method surface (governance-relevant subset)

The protocol frames in scope for any operational alert or audit log:

- **Connection**: `connection.start`, `connection.start-ok`, `connection.tune`, `connection.tune-ok`, `connection.open`, `connection.close`.
- **Channel**: `channel.open`, `channel.close`, `channel.flow` (deprecated for back-pressure — use `credit` semantics via confirm-mode).
- **Exchange**: `exchange.declare`, `exchange.bind`, `exchange.delete`.
- **Queue**: `queue.declare` (with arguments dict — see broker-extension table), `queue.bind`, `queue.purge`, `queue.delete`.
- **Basic**: `basic.publish`, `basic.consume`, `basic.ack`, `basic.nack`, `basic.reject`, `basic.qos` (prefetch).
- **Confirm**: `confirm.select`, `confirm.ack`, `confirm.nack` (broker-side publisher confirms).
- **Tx**: `tx.select`, `tx.commit`, `tx.rollback` (deprecated for high-throughput — use publisher confirms + idempotent producer pattern).

## Broker-extension arguments (x-headers) — policy table

These are RabbitMQ extensions to the AMQP 0-9-1 spec. They are first-class governance because they change delivery semantics:

| Argument | Default | Required value for orchestrators-managed brokers |
|---|---|---|
| `x-queue-type` | `classic` | `quorum` for replicated / durable workloads; `stream` for log-style offsets; `classic` for ephemeral queues |
| `x-message-ttl` | none | max 86 400 000 ms (24 h); broker warns on values ≥ this |
| `x-max-length` | none | bounded with overflow policy `x-overflow=reject-publish` (never `drop-head` for billing/telemetry) |
| `x-dead-letter-exchange` | none | configured per queue with explicit DLX topology |
| `x-priority` | none | 1..10 (max 10 priority levels in RabbitMQ 3.x) |
| `x-quorum-initial-group-size` | n/a | ≥ 3 for production quorum queues |

## Heartbeat / connection tuning

- **Heartbeat timeout (seconds)** — required field on `connection.tune`. Policy: `heartbeat = max(60, floor(negotiated_timeout / 2))`. Reject client-supplied values < 30.
- **Channel max** — default 0 (unlimited on server). Set client-side to ≤ 2047 to avoid mid-flight file descriptor exhaustion.
- **Frame max** — default 131072 (128 KiB). Reject client-supplied frame-max < 8192.

## Publisher confirms / consumer acknowledgement policy

- Producer must run in **confirm mode** for any queue type other than transient classic. Use `confirm.select` immediately after channel open.
- Consumer must use **manual ack** with `multiple=false` for at-least-once pipelines; `multiple=true` is permitted only for fan-out idempotent pipelines.
- Negative ack (`basic.nack`) must specify `requeue=false` when dead-lettering, `requeue=true` for transient retry.

## Version-driven compatibility risks

- `librabbitmq-c` 0.9.x predates RabbitMQ 3.x's queue-arguments validation; classic-vs-quorum confusion is the dominant production bug. `amqp091-go` v1.x is the only Go client currently receiving security patches.
- RabbitMQ 4.x disables classic mirroring by default; queues that previously relied on `x-ha-policy` will not be migrated automatically and must be re-declared as `x-queue-type=quorum`.

## Mandatory pre-flight (before declaring new client or broker version)

1. Confirm client library version against the supported matrix above; deprecate any client older than the broker's minimum-supported.
2. Inspect queue-arguments declarations for legacy x-headers not in the policy table; refuse drift unless explicitly approved in the change ticket.
3. Run a `rabbitmq-diagnostics check_running` against staging; confirm `Listener: amqp` advertises the supported protocols.
4. Validate publisher confirms end-to-end (`amqp091-go` test: 100k messages with `confirm.select`, zero nacks required).

## Sources

- AMQP 0-9-1 specification (OASIS): `https://www.amqp.org/specification/0-9-1`
- RabbitMQ AMQP 0-9-1 reference: `https://www.rabbitmq.com/amqp-0-9-1-reference.html`
- Quorum queues: `https://www.rabbitmq.com/docs/quorum-queues`
- Stream queues: `https://www.rabbitmq.com/docs/streams`
- Connection lifecycle: `https://www.rabbitmq.com/docs/connections`
