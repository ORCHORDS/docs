---
title: "HTTP/2 Protocol Version Guide (RFC 7540, updated by RFC 9113)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 7540 (May 2015); RFC 9113 (June 2022); https://www.rfc-editor.org/rfc/rfc7540 and /rfc/rfc9113"
---

# HTTP/2 Protocol Version Guide (RFC 7540, updated by RFC 9113)

## Scope

Reference card for HTTP/2 as specified in IETF RFC 7540 (May 2015) and updated by RFC 9113 (June 2022). Used by web platform, gateway, edge, and observability teams when documenting wire-level HTTP semantics for binary framing, stream multiplexing, header compression, and server push. Treats RFC 9113 as the current authoritative specification that obsoletes RFC 7540.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 9113, "HTTP/2" (June 2022) |
| Predecessor | RFC 7540 (May 2015) |
| Status | Internet Standard (RFC 9113) |
| Wire format | Binary framing layer; 9-byte fixed-length header |
| Framing concept | Connection, stream, frame (HEADERS, DATA, PRIORITY, RST_STREAM, SETTINGS, PING, GOAWAY, WINDOW_UPDATE, PUSH_PROMISE, CONTINUATION) |
| HPACK | RFC 7541 (header compression); RFC 9204 (QPING extension) |
| Error codes (selected) | PROTOCOL_ERROR (0x1), INTERNAL_ERROR (0x2), FLOW_CONTROL_ERROR (0x3), SETTINGS_TIMEOUT (0x4), FRAME_SIZE_ERROR (0x6), REFUSED_STREAM (0x7), CANCEL (0x8), CONNECT_ERROR (0xa), ENHANCE_YOUR_CALM (0xb), INADEQUATE_SECURITY (0xc) |
| Verification source | https://www.rfc-editor.org/rfc/rfc9113 and /rfc/rfc7541 |

## Plan

1. Identify the deployment context (edge proxy, origin server, gRPC endpoint, mobile API gateway, observability sidecar).
2. Map required features against RFC 9113 (binary framing, stream priorities, flow control, header compression) and the relevant updates (HPACK RFC 7541, RFC 8441 extended connect for WebSockets).
3. Capture the operational requirements: TLS termination upstream, ALPN negotiation ("h2"), connection coalescing, and server push deprecation guidance.
4. Validate against the live IANA HTTP/2 parameters registry and your edge or proxy configuration.

## Inputs

- TLS profile and ALPN advertisement (must include "h2" for h2-over-TLS deployments).
- Connection limits (max concurrent streams, initial window size, max frame size, header list size).
- Header configuration (HPACK table size, sensitive headers).
- Operational policy (connection coalescing rules, push policy, client IP propagation).

## ORCHORDS Profile

This guide is used as a reference when reviewing HTTP/2 deployment documentation or designing edge policy. It does NOT introduce protocol behavior beyond what RFCs specify. When a deployment requires a behavioral rule that is not captured here, escalate to a fresh review against the current RFC.

## Implementation Notes

- RFC 9113 obsoletes RFC 7540; deployments should reference RFC 9113 directly and treat RFC 7540 as historical.
- Server push is deprecated in RFC 9113; new designs should not rely on it.
- HPACK table sizes must match on both peers; mismatches cause decoder errors.
- Connection coalescing requires certificate SAN coverage across coalesced hosts; misconfiguration leaks traffic.
- HTTP/3 (RFC 9114, over QUIC) is recommended for new public-facing deployments where UDP is permitted.
- Prioritization and stream dependencies (RFC 9113 section 5.3) are advisory; do not rely on them for SLA enforcement.

## Companion Documents

- RFC 7541 (HPACK)
- RFC 8441 (extended connect / WebSockets over HTTP/2)
- RFC 9110 (HTTP semantics)
- RFC 9114 (HTTP/3)
- RFC 9000 (QUIC)
- IANA HTTP/2 Parameters registry
