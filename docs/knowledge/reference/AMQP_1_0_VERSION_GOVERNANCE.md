---
title: AMQP 1.0 Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: OASIS AMQP 1.0 (ISO/IEC 19464:2014); AMQP 1.0 Part 3 Messaging (OASIS, October 2012); AMQP 1.0 Errata 01 (October 2014); https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-overview-v1.0-os.html
---

# AMQP 1.0 Version Governance

## Scope

This card governs the AMQP 1.0 wire protocol as used by Azure Service Bus, ActiveMQ Artemis, Apache Qpid Broker-J, Apache Qpid C++ Broker, and Solace PubSub+. It is the reference input for AMQP 1.0 client implementations in Python (`python-qpid-proton`), Go (`qpid-proton-go`), .NET (`AmqpNetLite`), Java (`org.apache.qpid:qpid-jms-client`), and for any orchestrator that brokers AMQP 1.0 sessions with managed providers.

## Why this card exists

AMQP 1.0 is structurally different from AMQP 0-9-1: it is a framed, peer-to-peer, type-system-bearing protocol without broker-mediated queues in the wire definition. Confusion between the two creates routing failures (`NotFound`, `link-detach` storms) when an AMQP 0-9-1 idiom is attempted against an AMQP 1.0 endpoint.

## Version support matrix

| Spec version | OASIS status | ISO standard | Brokers supporting | Notes |
|---|---|---|---|---|
| AMQP 1.0 (base) | OASIS Standard 2012-10 | ISO/IEC 19464:2014 | Azure Service Bus, ActiveMQ Artemis, Qpid Broker-J 9.x, Qpid C++ 1.40+, Solace PubSub+ 9.x+ | core frame layout, performatives, transfer |
| AMQP 1.0 Part 3 (Messaging) | OASIS Standard 2012-10 | ISO/IEC 19464:2014 | same set as base | addressing, message format |
| AMQP 1.0 Errata 01 | OASIS 2014-10 | n/a | supported by qpid-proton 0.18+, Artemis 2.x | header / properties clarifications |
| AMQP 1.0 + (TBD) | working draft | n/a | experimental only in qpid-proton | not yet ratified — do not deploy |

References: `https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-overview-v1.0-os.html`, `https://docs.oasis-open.org/amqp/core/v1.0/errata01/os/amqp-core-errata01-v1.0-os.html`.

## Frame / performative surface (governance-relevant subset)

Every AMQP 1.0 client implementation must know how to issue and parse the following performatives, because every governance audit asks for them:

- **Open** — `container-id`, `hostname`, `max-frame-size`, `channel-max`, `idle-time-out`, `outgoing-locales`, `incoming-locales`, `offered-capabilities`, `desired-capabilities`.
- **Begin** — `remote-channel`, `next-outgoing-id`, `incoming-window`, `outgoing-window`, `handle-max`.
- **Attach** — `name`, `handle`, `role`, `snd-settle-mode`, `rcv-settle-mode`, `source`, `target`, `unsettled`, `incomplete-unsettled`, `initial-delivery-count`, `max-message-size`.
- **Flow** — `next-incoming-id`, `incoming-window`, `next-outgoing-id`, `outgoing-window`, `handle`, `delivery-count`, `link-credit`, `available`.
- **Transfer** — `handle`, `delivery-id`, `delivery-tag`, `message-format`, `settled`, `more`, `rcv-settle-mode`, `state`, `resume`, `aborted`, `batchable`.
- **Disposition** — `role`, `first`, `last`, `settled`, `state`, `batchable`.
- **Detach**, **End**, **Close**.

## Capability advertisement

AMQP 1.0 capability negotiation uses string identifiers in `offered-capabilities` / `desired-capabilities`:

- `ANONYMOUS-RELAY`
- `SHARED-SUBSCRIPTIONS` (broker-side, e.g. Service Bus topics with subscriptions)
- `MESSAGE-CLASS` (let the broker discriminate data vs control messages)
- `RECORDED-DELIVERY-COUNT` (Artemis 2.x feature)

A capability mismatch is not a connection failure — it is a soft failure that surfaces as link-detach with `amqp:not-implemented` or `amqp:invalid-field` and must be observable in the audit log.

## Settlement policy

| Pattern | Use case | Settle-mode pair |
|---|---|---|
| At-most-once | loss-tolerant telemetry, sample drains | `snd-settle-mode=settled`, `rcv-settle-mode=settled` |
| At-least-once | billing, telemetry, audit | `snd-settle-mode=unsettled`, `rcv-settle-mode=unsettled` (explicit `Disposition` ack) |
| Exactly-once | transactional state machines | `snd-settle-mode=mixed` (per-message override), `rcv-settle-mode=second`; with `RECORDED-DELIVERY-COUNT` |

## Link-credit and flow control

The producer-consumer flow control is **explicit**, not buffer-based. Every `Attach` carries `initial-delivery-count`; every `Flow` adjusts `link-credit`. Policy:

- Default `link-credit` = 30 for low-latency, 250 for throughput, 1024 for bulk streaming.
- Always set `rcv-settle-mode` explicitly; do not rely on broker default.
- Window tuning: `incoming-window` ≥ 4 × `link-credit` × max-message-size to absorb producer bursts.

## SASL / TLS integration

- AMQP 1.0 puts SASL **outside** the AMQP framing — it is a sibling layer (`AMQP-SASL-1.0` document). On TCP+TLS, the order is `tcp → tls → sasl-handshake → amqp-open`.
- Mandatory mechanisms: `PLAIN`, `SCRAM-SHA-1`, `SCRAM-SHA-256`. `ANONYMOUS` only for non-production or test.
- TLS 1.2 minimum; prefer TLS 1.3. `sasl=` vs `amqps=` URI scheme differs across providers — always verify the broker documentation.

## Mandatory pre-flight (before adopting AMQP 1.0 in a new component)

1. Confirm broker version supports AMQP 1.0 explicitly (some "AMQP-compatible" brokers speak 0-9-1 only — the most common vendor confusion).
2. Declare every capability that the client will use in `desired-capabilities`; refuse deployments that require a capability not in `offered-capabilities` of the staging broker.
3. Validate settlement mode end-to-end: send 1000 messages, count explicit `Disposition` acks, ensure 100% match.
4. Confirm `idle-time-out` policy: server-supplied value, client must echo in `Open`. Reject client attempts to negotiate `idle-time-out=0` (no keepalive).

## Sources

- OASIS AMQP 1.0 core: `https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-overview-v1.0-os.html`
- OASIS AMQP 1.0 messaging: `https://docs.oasis-open.org/amqp/core/v1.0/os/amqp-core-messaging-v1.0-os.html`
- AMQP 1.0 Errata 01: `https://docs.oasis-open.org/amqp/core/v1.0/errata01/os/amqp-core-errata01-v1.0-os.html`
- Apache Qpid Proton (canonical C ref impl): `https://qpid.apache.org/components/proton/`
- Azure Service Bus AMQP 1.0 protocol guide: `https://learn.microsoft.com/azure/service-bus-messaging/service-bus-amqp-protocol-guide`
