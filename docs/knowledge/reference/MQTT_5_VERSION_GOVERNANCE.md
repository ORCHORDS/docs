---
title: MQTT v5 Version Governance (OASIS, ISO/IEC 20922)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: OASIS MQTT v5.0 (March 2019); ISO/IEC 20922:2016 (MQTT v3.1.1); OASIS MQTT v5.0 Errata 01 (April 2024); https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html
---

# MQTT v5 Version Governance (OASIS, ISO/IEC 20922)

## Scope

This card governs how `orchords-docs` selects, deploys, and operates MQTT v5 brokers and clients. It is the reference input for the IoT reference architecture, the edge-collector service, and any fleet-management integration that uses MQTT for control-plane telemetry.

## Why this card exists

MQTT v3.1.1 (ISO/IEC 20922) is a tight, fixed-payload protocol that makes most operational decisions explicit (QoS, retain, will message). MQTT v5 added properties, reason codes, shared subscriptions, topic aliases, and flow-control semantics that are opt-in. A KB card that recommends "MQTT" without a version pin produces a fleet where brokers and clients disagree about feature support and silently fall back to v3.1.1 semantics.

## Version support matrix

| Spec | Status | Brokers supporting | Clients supporting |
|---|---|---|---|
| MQTT v3.1 | OASIS Standard 2010 | legacy | legacy Eclipse Paho 1.x |
| MQTT v3.1.1 | OASIS Standard 2014, ISO/IEC 20922:2016 | Mosquitto 1.5+, HiveMQ 4.x, EMQX 4.x+ | Paho 1.2+, HiveMQ MQTT Client 1.x, Go `paho.golang` |
| MQTT v5.0 | OASIS Standard 2019 | Mosquitto 2.0+, HiveMQ 4.4+, EMQX 4.4+, AWS IoT Core, Azure IoT Hub | Paho 2.0+ (Java/C/Python/Go), HiveMQ MQTT Client 1.3+, AsyncMQTT 5.0+ |
| MQTT v5.0 Errata 01 | OASIS 2024-04 | HiveMQ 4.31+, EMQX 5.7+, Mosquitto 2.0.20+ | Paho 2.1+, AsyncMQTT 5.1+ |

References: `https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html`, `https://docs.oasis-open.org/mqtt/mqtt/v5.0/errata01/os/mqtt-v5.0-errata01-os.html`.

## CONNECT packet governance (v5 properties)

The CONNECT packet in v5 carries a property list that controls connection-time behavior:

| Property | Identifier | Required value |
|---|---|---|
| `Session Expiry Interval` | 0x11 | `0` for clean sessions, otherwise seconds; max 4 294 967 295 (~ 136 years) |
| `Receive Maximum` | 0x19 | ≤ 65 535 |
| `Maximum Packet Size` | 0x27 | 1 — 2 147 483 647 (4 GiB); broker should not exceed the negotiated value |
| `Topic Alias Maximum` | 0x22 | ≤ 65 535 |
| `Request Response Information` | 0x17 | `1` to request response info |
| `Request Problem Information` | 0x17 | `1` to receive human-readable problem details |
| `User Property` | 0x26 | free-form key/value; allowed multiple |
| `Authentication Method` | 0x15 | used for challenge/response |
| `Authentication Data` | 0x16 | challenge/response payload |

## CONNACK packet governance

The CONNACK packet carries:

| Field | Purpose |
|---|---|
| `Session Present` | `1` if the broker resumed an existing session |
| `Connect Reason Code` | `0x00` Success, `0x80` Unspecified error, `0x81` Malformed packet, `0x82` Protocol error, `0x86` Bad user/pass, `0x8A` Banned |
| `Receive Maximum` | broker-proposed limit on in-flight QoS 1 / QoS 2 publishes |
| `Maximum QoS` | `0` or `1` or `2` |
| `Retain Available` | `0` if retain is unavailable |
| `Maximum Packet Size` | broker-side cap |
| `Assigned Client Identifier` | required if client sent empty Client ID |
| `Topic Alias Maximum` | broker-proposed cap |
| `Reason String` | human-readable, optional |
| `Response Information` | request-response info, if requested |
| `Server Reference` | alternate broker URI for client to reconnect to |
| `User Property` | free-form |

## Subscription options (v5)

The SUBSCRIBE packet carries Subscription Options with new v5 fields:

| Field | Values |
|---|---|
| `QoS` | `0`, `1`, `2` |
| `No Local` | `1` to disable forwarding of messages published by the same client |
| `Retain As Published` | `1` to retain the original PUBLISH retain flag |
| `Retain Handling` | `0` send retained at subscribe, `1` send only if subscription is new, `2` do not send retained |
| `Subscription Identifier` | integer to correlate messages to subscriptions |

## Reason codes

Every ACK packet (PUBACK, PUBREC, PUBREL, PUBCOMP, SUBACK, UNSUBACK, DISCONNECT, AUTH) carries a single byte reason code. The KB reference card must enumerate the codes in use; the broker emits `0x00` Success unless noted. A non-success reason code in DISCONNECT signals the broker is closing the session and the client should reconnect to `Server Reference` if present.

## Flow control and in-flight quota

QoS 1 and QoS 2 publishes consume in-flight quota. The client enforces `min(client Receive Maximum, broker Receive Maximum)`. When in-flight quota reaches 0, the client must stop publishing QoS 1 / QoS 2 messages until acks arrive.

## Shared subscriptions

MQTT v5 introduces shared subscriptions: `$share/<ShareName>/<TopicFilter>`. The broker load-balances messages across the subscribed client group. Required for any horizontal-scaling use case.

## Mandatory pre-flight (before adopting a new broker version)

1. Confirm broker version supports MQTT v5.0 (and Errata 01 if cited).
2. Confirm client library version is within the supported matrix above.
3. Validate broker advertises the supported CONNACK properties (`Receive Maximum`, `Maximum QoS`, `Topic Alias Maximum`, etc.).
4. Validate shared subscriptions work end-to-end (`$share/<name>/<topic>`) under at least 2 client connections.
5. Validate retain handling and topic alias under load.
6. Validate `Reason String` and `Response Information` propagation in the audit log.

## Security

- TLS 1.3 mandatory on every public-facing MQTT broker.
- Authentication via username/password, X.509 client cert, or OAuth 2.0 bearer token (via v5 `Authentication Method`).
- Authorization enforced at topic level (`$share/...` topics must be authorized identically to the underlying topic).
- Reject v3.1.1 connections to any broker that also offers v5; offer v5 only on dedicated listener unless legacy is documented as supported.

## Sources

- OASIS MQTT v5.0: `https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html`
- OASIS MQTT v5.0 Errata 01: `https://docs.oasis-open.org/mqtt/mqtt/v5.0/errata01/os/mqtt-v5.0-errata01-os.html`
- ISO/IEC 20922:2016 (MQTT v3.1.1): `https://www.iso.org/standard/69466.html`
- HiveMQ MQTT essentials: `https://www.hivemq.com/mqtt/`
- Eclipse Paho: `https://www.eclipse.org/paho/`
