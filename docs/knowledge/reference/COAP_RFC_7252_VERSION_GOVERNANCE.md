---
title: CoAP Version Governance (RFC 7252, RFC 7641, RFC 7959, RFC 8323, RFC 8613, RFC 8974)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: IETF RFC 7252 (June 2014); RFC 7641 (September 2015); RFC 7959 (August 2016); RFC 8323 (June 2018); RFC 8613 (July 2019); RFC 8974 (January 2021); https://www.rfc-editor.org/rfc/rfc7252
---

# CoAP Version Governance (RFC 7252, RFC 7641, RFC 7959, RFC 8323, RFC 8613, RFC 8974)

## Scope

This card governs how `orchords-docs` evaluates Constrained Application Protocol (CoAP) and its extensions. CoAP is the IETF standard for resource-constrained devices (smart sensors, smart meters, wearables, industrial sensors) running on UDP or DTLS. It is the reference input for any IoT reference architecture cited from the KB.

## Why this card exists

CoAP is layered: the base protocol (RFC 7252) defines request/response semantics; RFC 7641 adds Observe; RFC 7959 adds Block-Wise transfers; RFC 8323 brings CoAP over TCP/TLS; RFC 8613 brings OSCORE (object security); RFC 8974 profiles CoAP for use with TCP, TLS, and WebSockets. A KB card that cites "CoAP" without enumerating the supporting RFCs cannot reconcile client/server interop failures.

## Protocol version support matrix

| Spec | Status | Notes |
|---|---|---|
| RFC 7252 — CoAP base | IETF Standard (June 2014) | mandatory baseline |
| RFC 7641 — Observe | IETF Standard (September 2015) | optional |
| RFC 7959 — Block-Wise | IETF Standard (August 2016) | optional |
| RFC 8132 — PATCH/ FETCH (now superseded by RFC 8132 errata in RFC 9177) | IETF | for firmware / bulk update |
| RFC 8323 — TCP/TLS/WebSocket | IETF Standard (June 2018) | optional |
| RFC 8613 — OSCORE | IETF Standard (July 2019) | mandatory for new constrained-network security |
| RFC 8974 — TCP/TLS profile | IETF Standard (January 2021) | reconciles RFC 8323 |
| RFC 9175 — CoAP over unreliable datagram | draft (2022) | alignment with QUIC |
| RFC 9177 — CoAP use with HTTP | draft (2022) | mapping CoAP resources to HTTP |

References: `https://www.rfc-editor.org/rfc/rfc7252`, `https://www.rfc-editor.org/rfc/rfc7641`, `https://www.rfc-editor.org/rfc/rfc7959`, `https://www.rfc-editor.org/rfc/rfc8323`, `https://www.rfc-editor.org/rfc/rfc8613`, `https://www.rfc-editor.org/rfc/rfc8974`.

## Message surface

| Message type | Field | Notes |
|---|---|---|
| CON (Confirmable) | T=0 | requires ACK; retransmit on timeout |
| NON (Non-confirmable) | T=1 | no ACK; used for one-way telemetry |
| ACK | T=2 | response to CON |
| RST | T=3 | reset; rejects a CON or NON |

## Method surface

| Method | RFC | Notes |
|---|---|---|
| GET | RFC 7252 | resource retrieval |
| POST | RFC 7252 | resource creation / processing |
| PUT | RFC 7252 | resource update |
| DELETE | RFC 7252 | resource deletion |
| FETCH | RFC 8132/9177 | partial resource retrieval |
| PATCH | RFC 8132/9177 | partial resource update |
| iPATCH | RFC 8132 | idempotent PATCH |

## Transport bindings

| Binding | Use case | Required |
|---|---|---|
| CoAP over UDP | baseline | yes |
| CoAP over DTLS 1.2/1.3 | baseline for unsecured UDP | yes (when security needed) |
| CoAP over TCP | bulk transfers, NAT-traversal | optional |
| CoAP over TLS | bulk transfers with security | optional |
| CoAP over WebSocket | browser-facing or WebSocket-friendly transports | optional |
| CoAP over QUIC | unreliable networks | emerging |

References: `https://www.rfc-editor.org/rfc/rfc7252` § 3, RFC 8323 § 3.

## Observe (RFC 7641)

- The client issues a GET request with the `Observe` option (`Observe = 0`).
- The server registers the observer and emits notifications as the resource changes.
- Notifications carry an incrementing `Observe` sequence number.
- Cancellation: client sends GET with `Observe = 1` to deregister.

## Block-Wise transfers (RFC 7959)

| Field | Use case |
|---|---|
| Block1 | used in request body for large POST / PUT / PATCH |
| Block2 | used in response body for large GET |
| Block size | 16, 32, 64, 128, 256, 512, 1024 bytes |
| More flag (`M`) | indicates more blocks follow |

## OSCORE (RFC 8613)

Object Security for CoAP (OSCORE) provides end-to-end security at the CoAP message layer:

- Replaces DTLS with per-message AEAD.
- Compression-friendly: small message expansion (~ 8 bytes overhead).
- Works over any transport (UDP, TCP, WebSocket, SMS, NB-IoT).
- Uses COSE (RFC 9052, RFC 9053) for cryptographic operations.

OSCORE policy:

- OSCORE is mandatory for new constrained-network deployments.
- DTLS may be used as a fallback for legacy devices; new devices must support OSCORE.

## CoAP security profile

| Layer | Mandatory |
|---|---|
| DTLS 1.3 (RFC 9147) or OSCORE (RFC 8613) | yes |
| ECDHE key exchange (X25519 or P-256) | yes |
| AEAD cipher: AES-128-GCM or ChaCha20-Poly1305 | yes |
| Replay window | yes |
| Certificate validation | yes (when using certificates) |
| Raw public-key (RFC 7250) | optional |

References: `https://www.rfc-editor.org/rfc/rfc8613`, `https://www.rfc-editor.org/rfc/rfc9147`.

## CoAP over TCP/TLS profile (RFC 8974)

RFC 8974 reconciles RFC 8323 with TLS 1.3 profile:

- TLS 1.3 mandatory.
- Cipher suites: TLS_AES_128_GCM_SHA256, TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256.
- Key share: X25519 preferred.
- CoAP over TCP uses the default CoAP port 5683; CoAP over TLS uses 5684.
- Block size for bulk transfer on TCP: ≤ 1024 bytes.

## Mandatory pre-flight (before adopting a new CoAP deployment)

1. CoAP version (1) is supported on the client and server.
2. Confirm OSCORE is supported for new deployments.
3. Confirm TLS 1.3 profile for TCP-bound deployments.
4. Confirm Block-Wise transfer is configured for large payloads.
5. Confirm Observe is wired (where applicable) with cancellation handling.
6. Validate retransmit logic: 4 retransmits, exponential backoff starting at `ACK_TIMEOUT` = 2 seconds, `ACK_RANDOM_FACTOR` = 1.5.

## Observability

- `coap.request.count` (counter, by method)
- `coap.response.count` (counter, by code)
- `coap.response.latency_ms` (histogram)
- `coap.observe.active.count` (gauge)
- `coap.retransmit.count` (counter)
- `coap.block.transfer.bytes` (counter)
- `coap.oscore.security.failures.count` (counter)

## Sources

- RFC 7252: `https://www.rfc-editor.org/rfc/rfc7252`
- RFC 7641: `https://www.rfc-editor.org/rfc/rfc7641`
- RFC 7959: `https://www.rfc-editor.org/rfc/rfc7959`
- RFC 8323: `https://www.rfc-editor.org/rfc/rfc8323`
- RFC 8613: `https://www.rfc-editor.org/rfc/rfc8613`
- RFC 8974: `https://www.rfc-editor.org/rfc/rfc8974`
- RFC 9175: `https://www.rfc-editor.org/rfc/rfc9175`
- IETF CoRE Working Group: `https://datatracker.ietf.org/wg/core/about/`
