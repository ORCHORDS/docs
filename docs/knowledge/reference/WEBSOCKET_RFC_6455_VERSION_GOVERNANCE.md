---
title: "WebSocket Protocol (RFC 6455) Version Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 6455 (December 2011); RFC 9220 (June 2022); RFC 8441 (September 2018); https://www.rfc-editor.org/rfc/rfc6455"
---

# WebSocket Protocol (RFC 6455) Version Governance

## Purpose

This card governs how ORCHORDS references the WebSocket protocol: the framing, the opening-handshake upgrade flow, masking rules for client-to-server traffic, and the relationship between WebSocket and HTTP/1.1, HTTP/2, and HTTP/3.

## Canonical Reference

- IETF RFC 6455 — *The WebSocket Protocol*, December 2011
- IETF RFC 9220 — *Bootstrapping WebSockets over HTTP/2*, June 2022
- IETF RFC 8441 — *Bootstrapping WebSockets over HTTP/3*, September 2018
- Companion: RFC 7230 (HTTP/1.1), RFC 7540 (HTTP/2), RFC 9113 (HTTP/2 update), RFC 9114 (HTTP/3)

## Core Properties

- **Framing** — Each WebSocket frame begins with a 1-byte FIN/RSV/opcode header, a 1-byte mask + payload-length field, a 4-byte masking key (when masked), and the payload. RFC 6455 §5.2.
- **Opening handshake** — HTTP/1.1 `Upgrade: websocket` with `Connection: Upgrade`, `Sec-WebSocket-Key`, `Sec-WebSocket-Version: 13`, and `Sec-WebSocket-Accept` response. RFC 6455 §4.
- **Subprotocol negotiation** — `Sec-WebSocket-Protocol` carries a comma-separated list of application subprotocols; server picks one. RFC 6455 §1.9.
- **Masking** — Client-to-server frames MUST be masked with a 32-bit key; server-to-client frames MUST NOT be masked. RFC 6455 §5.3. This mitigates cache-poisoning attacks that historically affected intermediary caches.
- **Control frames** — Close (0x8), Ping (0x9), Pong (0xA). Control frames may be interleaved with fragmented data frames and MUST NOT carry payload > 125 bytes.
- **HTTP/2 and HTTP/3 bootstrapping** — RFC 9220 uses `CONNECT` with `:protocol = websocket` pseudo-header over HTTP/2 (extended CONNECT); RFC 8441 does the same for HTTP/3. Masking is no longer required for HTTP/2+ because headers are HPACK/QPACK-compressed and intermediaries cannot be confused into injecting frames.

## Migration and Version Drift

| WebSocket variant | Transport | Spec | Notes |
| --- | --- | --- | --- |
| "WebSocket" — HyBi 13 | HTTP/1.1 upgrade | RFC 6455 | Baseline; masking required for client→server |
| WS-over-HTTP/2 | HTTP/2 `:protocol` | RFC 9220 | Used by gRPC-Web and some reverse-proxy setups; no client masking |
| WebTransport (note: not WS) | HTTP/3 | RFC 9298 | Often confused with WebSocket but uses QUIC datagrams/streams |

## Deprecations and Replacements

- The older "Hixie" drafts (draft-hixie-thewebsocketprotocol-75 and earlier) are obsolete. RFC 6455 §1.6 specifies `Sec-WebSocket-Version: 13` as the only current version. Clients offering any other version MUST be rejected.
- Compression — `permessage-deflate` (RFC 7692) is widely implemented but historically the source of CRIME-style side-channel attacks if applied to authenticated traffic. Treat as opt-in per message type.

## Usage in ORCHORDS

- WebSocket is appropriate for full-duplex low-latency push (live dashboards, collaborative editing, agent streams).
- For new services that can run over HTTP/2 or HTTP/3, prefer RFC 9220/8441 bootstrapping — it removes the client-masking requirement and plays correctly with HTTP/2 stream multiplexing.
- For binary agent telemetry where ordered delivery and partial reliability are not required, consider WebTransport over QUIC instead.

## Open Items

- Monitor IETF discussion around WebSocket-over-HTTP/3 extensions to `permessage-deflate`.
- Track QUIC working group output for sub-protocol coexistence with WebSocket in mixed deployments.
