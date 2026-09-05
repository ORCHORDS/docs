---
title: NATS Messaging Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NATS documentation; Synadia; CNCF NATS project; nats.io
---

# NATS Messaging Version Governance

## Scope

This card governs how `orchords-docs` evaluates NATS — both the core broker and JetStream persistence — across versions, protocols, and deployment topologies.

## Why this card exists

NATS is the canonical cloud-native messaging system (CNCF graduated, March 2025). Without an explicit card, the KB cites NATS practices that ignore JetStream persistence model, subject-based addressing, and security best-practices.

## Versions

| Version | Status |
|---|---|
| 1.x | legacy core |
| 2.0–2.6 | legacy 2.x |
| 2.7–2.10 | current LTS |
| 2.11 | current |

References: `https://github.com/nats-io/nats-server/releases`.

## Protocols

| Protocol | Use |
|---|---|
| NATS (text) | core pub/sub |
| NKEY | Ed25519-based identity |
| JWT | identity claims |
| TLS | transport encryption |
| WebSocket | browser clients |
| Leafnode | edge-to-core bridging |

References: `https://docs.nats.io/reference/reference-protocols`.

## Subject addressing

NATS uses hierarchical subject addresses:

- `orders.created` — dot-separated tokens.
- `orders.*.us` — single-token wildcard.
- `orders.>` — multi-token wildcard.

Subject normalization rules:

- Tokens are case-sensitive.
- Whitespace is preserved.
- Empty tokens (`..`) are forbidden.

## JetStream

JetStream is the persistence layer:

- Streams: durable, ordered, replayable.
- Consumers: pull, push, durable, queue.
- Retention: limits, interest, work-queue.
- Acknowledgement: explicit, ack, ack-publish, nack, term.

References: `https://docs.nats.io/nats-concepts/jetstream`.

## Authentication and authorization

| Method | Use |
|---|---|
| Token | single static token |
| User / Password | basic auth |
| NKEY | Ed25519 keys |
| JWT | per-user claims + scopes |
| Decentralized JWT | decentralized trust |
| Delegated JWT | central auth server |

References: `https://docs.nats.io/running-a-nats-service/configuration/securing_nats/auth_intro`.

## Cross-reference

| Domain | Card |
|---|---|
| Kafka | `KAFKA_KIP_VERSION_GOVERNANCE.md` |
| AMQP | `AMQP_0_9_1_VERSION_GOVERNANCE.md`, `AMQP_1_0_VERSION_GOVERNANCE.md` |
| MQTT | `MQTT_5_VERSION_GOVERNANCE.md` |

## Sources

- NATS documentation: `https://docs.nats.io/`
- NATS GitHub: `https://github.com/nats-io/nats-server`
- Synadia: `https://synadia.com/`
