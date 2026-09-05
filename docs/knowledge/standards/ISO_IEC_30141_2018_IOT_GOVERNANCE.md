---
title: ISO/IEC 30141:2018 IoT Reference Architecture Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 30141:2018 (first edition, 2018-08) — "Information technology — Internet of Things — Reference architecture"; https://www.iso.org/standard/65695.html
---

# ISO/IEC 30141:2018 IoT Reference Architecture Governance

## Scope

This card governs how `orchords-docs` evaluates IoT reference architectures against ISO/IEC 30141:2018. It is the reference input for any KB card that describes an IoT system, smart-device deployment, or industrial sensor network.

## Why this card exists

ISO/IEC 30141 is the canonical IoT reference architecture (IoT RA) standard. It defines five architectural viewpoints (AV), six system characteristics, and a domain model that the KB must align with. Without an explicit card, KB IoT descriptions drift from the standard.

## Document structure (Clauses 6 — 11)

| Clause | Title | Project interpretation |
|---|---|---|
| 6 | Concepts | IoT vocabulary |
| 7 | IoT domain model | entity-relationship view of IoT |
| 8 | IoT conceptual model | abstract components |
| 9 | IoT reference architecture | the canonical 5-viewpoint model |
| 10 | Implementation view | how to realize the IoT |
| 11 | Compliance | conformance criteria |

References: `https://www.iso.org/standard/65695.html`.

## Five architectural viewpoints

| View | Stakeholder |
|---|---|
| AV-1 — Usage View | users, business stakeholders |
| AV-2 — Functional View | system designers, integrators |
| AV-3 — System View | system architects |
| AV-4 — Communication View | network engineers |
| AV-5 — Information View | data architects |

## Six system characteristics

| Characteristic | Description |
|---|---|
| Network connectivity | devices are addressable and reachable |
| Scalability | system scales with device and data volume |
| Safety | system does not pose a risk to physical safety |
| Security | system protects against unauthorized access |
| Privacy | system protects personal information |
| Manageability | system is operable and maintainable |

## Domain model

ISO/IEC 30141 defines four primary entities:

- **Entity** — anything that exists, can be identified, and is of interest (a thing, person, place, process, ...).
- **Virtual Entity** — digital representation of an entity.
- **IoT Service** — service exposed by the IoT system to interact with entities.
- **Resource** — software artifact (memory, CPU, network) exposed by devices.

The relationships:

- Entities are sensed or actuated by Devices (subclass of Resources).
- Virtual Entities correspond to Entities and are operated on by IoT Services.

## Functional view (AV-2)

The AV-2 functional view decomposes the IoT into functional components:

- **Device** — sensor/actuator with network interface.
- **Communication** — networking capability.
- **Service** — application-level capability.
- **Management** — device management, configuration, monitoring.
- **Security** — authentication, authorization, encryption.
- **Application** — user-facing capability.

## Communication view (AV-4)

The communication view enumerates:

- **Application protocols** — CoAP (RFC 7252), MQTT (OASIS), HTTP/3 (RFC 9114), LwM2M (OMA).
- **Transport protocols** — UDP, TCP, QUIC, NB-IoT, LoRaWAN, SigFox.
- **Device identity** — EUI-64, IPv6 6LoWPAN, IEEE 802.15.4.
- **Routing** — RPL (RFC 6550), 6LoWPAN.

## Information view (AV-5)

The information view enumerates:

- **Data formats** — CBOR (RFC 8949), SenML (RFC 8428), JSON, Protobuf.
- **Semantics** — oneM2M base ontology, W3C WoT TD, schema.org IoT extensions.
- **Storage** — time-series (InfluxDB, TimescaleDB), document (MongoDB), object (S3).
- **Exchange** — message queue (Kafka, RabbitMQ), pub/sub (MQTT, AMQP).

## Implementation view

Implementation considerations:

- Device class hierarchy: Class 0 (very constrained, ~ 10 KiB RAM), Class 1 (constrained, ~ 100 KiB RAM), Class 2 (non-constrained, ≥ 50 MiB RAM).
- Operating system: Contiki, RIOT, Zephyr, FreeRTOS, Linux (Class 2+).
- Connectivity: Wi-Fi, Bluetooth LE, Zigbee, Thread, NB-IoT, LoRaWAN, SigFox.

## Compliance

A KB card that cites an IoT reference architecture must declare:

- The viewpoint(s) it addresses (AV-1 through AV-5).
- The six system characteristics it claims (network connectivity, scalability, safety, security, privacy, manageability).
- The domain entities it includes (Entities, Virtual Entities, IoT Services, Resources).
- The cross-reference to other governance cards (CoAP, LwM2M, MQTT, 3GPP).

## Mandatory pre-flight (before adopting a new IoT component)

1. The component fits one of the five architectural viewpoints.
2. The six system characteristics are documented for the component.
3. The applicable transport / application protocols are documented.
4. The data format is documented.
5. The compliance criteria are documented.

## Cross-reference

| Component | Card |
|---|---|
| CoAP | `COAP_RFC_7252_VERSION_GOVERNANCE.md` |
| CBOR | `CBOR_RFC_8949_VERSION_GOVERNANCE.md` |
| LwM2M | `LWM2M_RFC_9195_VERSION_GOVERNANCE.md` |
| MQTT | `MQTT_5_VERSION_GOVERNANCE.md` |
| HTTP/3 | `HTTP_3_RFC_9114_VERSION_GOVERNANCE.md` |
| RPL (RFC 6550) | n/a (out of scope) |

## Self-attestation cycle

Every 180 days:

1. Walk every IoT reference card.
2. Confirm conformance to the five viewpoints and six characteristics.
3. Update the next-review date.

## Sources

- ISO/IEC 30141:2018: `https://www.iso.org/standard/65695.html`
- IoT-A Project deliverable (predecessor): `http://www.iot-a.eu/`
- oneM2M base ontology: `http://www.onem2m.org/`
- W3C Web of Things Thing Description: `https://www.w3.org/TR/wot-thing-description11/`
- IETF CoRE WG: `https://datatracker.ietf.org/wg/core/about/`
