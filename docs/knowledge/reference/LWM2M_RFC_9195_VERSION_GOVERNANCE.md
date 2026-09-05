---
title: LwM2M Version Governance (OASIS, OMA SpecWorks)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: OMA SpecWorks LwM2M 1.0 (February 2017); LwM2M 1.1 (June 2018); LwM2M 1.2 (November 2020); LwM2M 2.0 (2024); https://technical.openmobilealliance.org/OMNA/LwM2M/LwM2MRegistry.html
---

# LwM2M Version Governance (OASIS, OMA SpecWorks)

## Scope

This card governs how `orchords-docs` evaluates Lightweight M2M (LwM2M) — the OMA SpecWorks standard for device management and application data exchange on constrained IoT devices. LwM2M runs on top of CoAP (RFC 7252), with DTLS for security.

## Why this card exists

LwM2M separates device management (LwM2M Server / Client) from application data (LwM2M Object), with a well-defined Object Model that maps every resource to a CoAP path. The protocol versions (1.0, 1.1, 1.2, 2.0) added features such as Transport Layer Security improvements, new Object instances, and updated firmware update procedures. A KB card that cites LwM2M without binding to a version produces an interop story that breaks when objects are re-negotiated.

## Document set

- **OMA LwM2M 1.0** (February 2017) — base, server-side bootstrap, UDP and SMS transport.
- **OMA LwM2M 1.0.1 / 1.0.2** (2018 / 2019) — errata.
- **OMA LwM2M 1.1** (June 2018) — adds HTTP, MQTT, and TCP transports; LwM2M 1.1 multi-instance bootstrap.
- **OMA LwM2M 1.2** (November 2020) — adds dynamic resource observation, improved firmware update, additional objects.
- **OMA LwM2M 2.0** (2024) — adds native CBOR encoding, support for LwM2M Objects over LwM2M v2 protocol.

References: `https://technical.openmobilealliance.org/OMNA/LwM2M/LwM2MRegistry.html`, `https://www.openmobilealliance.org/release/LwM2M/`.

## Transport bindings

| Version | UDP | SMS | TCP | HTTP | MQTT | NB-IoT | CoAP over QUIC |
|---|---|---|---|---|---|---|---|
| 1.0 | yes | yes | no | no | no | no | no |
| 1.1 | yes | yes | yes | yes | yes | yes | no |
| 1.2 | yes | yes | yes | yes | yes | yes | no |
| 2.0 | yes | yes | yes | yes | yes | yes | yes |

## Object model

LwM2M objects are defined by an `Object ID`, `Instance ID`, `Resource ID`, and a `Resource Instance ID`. The URI is:

```
/{Object ID}/{Object Instance ID}/{Resource ID}/{Resource Instance ID}
```

For example: `/3/0/9` is `Device / 0 / Battery Level / (single instance)`.

Mandatory objects (subset):

| Object | ID | Purpose |
|---|---|---|
| LwM2M Security | 0 | security configuration |
| LwM2M Server | 1 | server connectivity |
| Access Control | 2 | access rights per object |
| Device | 3 | device metadata |
| Connectivity Monitoring | 4 | network connectivity stats |
| Firmware Update | 5 | firmware update procedures |
| Location | 6 | geolocation |
| Connectivity Statistics | 7 | traffic stats |

References: OMA LwM2M Object Registry.

## Operations (operations surface)

| Operation | Verb |
|---|---|
| Read | CoAP GET |
| Write | CoAP PUT |
| Write-Attributes | CoAP PUT (with attrs) |
| Execute | CoAP POST |
| Create | CoAP POST |
| Delete | CoAP DELETE |
| Discover | CoAP GET (root / `?rt`) |
| Observe | CoAP GET with Observe |
| Write Composite | CoAP PUT (multi-resource) |

## Security

| LwM2M version | Default security |
|---|---|
| 1.0 | DTLS 1.2 (PSK, Raw Public Key, X.509) |
| 1.1 | DTLS 1.2 (PSK, RPK, X.509) + improvements |
| 1.2 | DTLS 1.2 + 1.3 support added |
| 2.0 | DTLS 1.3 + OSCORE |

Policy:

- DTLS 1.3 mandatory for new deployments.
- OSCORE supported where transport is UDP.
- Pre-shared key (PSK) or X.509 certificates preferred.
- Raw Public Key (RFC 7250) allowed for low-bandwidth deployments.
- Bootstrap Server (BS) enforces the device's bootstrap flow.

## Bootstrap

The bootstrap sequence differs between versions:

- **LwM2M 1.0** — Client initiated (factory bootstrap) or server initiated (bootstrap from server URI).
- **LwM2M 1.1** — Multi-instance bootstrap: multiple servers can be bootstrapped.
- **LwM2M 1.2** — Improved bootstrap error handling, retry policy.
- **LwM2M 2.0** — Bootstrap over CoAP+OSCORE, with LwM2M v2 Object Model.

## Firmware update

LwM2M Firmware Update Object (ID 5) defines:

- Package URI (download URL).
- Package integrity verification (hash).
- Update execution (atomic state machine: Idle → Downloading → Downloaded → Updating → Updating with Failure → Idle).
- Update delivery methods (pull vs push).

Policy:

- Firmware update packages must be signed (COSE_Sign1 per `CBOR_RFC_8949_VERSION_GOVERNANCE.md`).
- Atomicity: a failed update must roll back to the prior firmware.
- Update channel: TLS 1.3 + pinned server cert.

## Mandatory pre-flight (before adopting a new LwM2M deployment)

1. LwM2M version is supported on client and server.
2. Transport binding is supported on both ends.
3. Object set is published.
4. Bootstrap flow is documented.
5. Security profile is documented (DTLS version, cipher suite, key exchange).
6. Firmware update procedure is signed and atomic.

## Sources

- OMA LwM2M 1.0 Specification: `https://www.openmobilealliance.org/release/LwM2M/`
- OMA LwM2M 1.1 Specification: same registry, version-tagged
- OMA LwM2M 1.2 Specification: same registry, version-tagged
- OMA LwM2M Object Registry: `https://technical.openmobilealliance.org/OMNA/LwM2M/LwM2MRegistry.html`
- OMA LwM2M Transport Bindings: `https://www.openmobilealliance.org/release/LwM2M/`
- RFC 7250 (RPK): `https://www.rfc-editor.org/rfc/rfc7250`
