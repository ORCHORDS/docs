---
title: "HTTP/3 Version Governance (RFC 9114)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 9114; https://www.rfc-editor.org/rfc/rfc9114"
---

# HTTP/3 Version Governance (RFC 9114)

## Scope

Reference card for HTTP/3 as defined by IETF RFC 9114. Used by platform, web, and operations teams when documenting HTTP-layer deployments over QUIC, HTTP/3 framing, header compression (QPACK), or interop with earlier HTTP versions. Treats RFC 9114 as the authoritative HTTP-over-QUIC layer, with RFC 9000 (QUIC), RFC 9001 (TLS in QUIC), RFC 9204 (QPACK), RFC 9218 (HTTP Priorities), RFC 9221 (Bootstrapping WebSockets over HTTP/3), RFC 9298 (CONNECT-UDP), and RFC 9527 (Origin Validation Subdomains) as companion documents.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 9114, "HTTP/3" |
| Status | Proposed Standard |
| Transport | QUIC (RFC 9000) |
| TLS | RFC 9001 (using TLS 1.3 per RFC 8446) |
| Header compression | QPACK (RFC 9204) |
| Priorities | RFC 9218 |
| Verification source | https://www.rfc-editor.org/rfc/rfc9114 and IANA HTTP/3 registries |

## Plan

1. Identify the deployment context (origin server, edge proxy, CDN, browser client, native client, IoT client).
2. Map required behaviour against RFC 9114 § 3–§ 7 (HTTP message semantics on QUIC streams, request/response framing, field section representation, trailers, control streams, error handling).
3. Capture operational requirements: QUIC version negotiation per RFC 9000 § 7.1, QPACK encoder/decoder streams configuration (RFC 9204), HTTP/3 priorities (RFC 9218), HTTP/3 settings frame, and HTTP/3 ORIGIN frame for origin validation (RFC 9527).
4. Validate against the live IANA HTTP/3 registries (HTTP/3 Settings, HTTP/3 Error Codes, HTTP/3 Frame Types, Origin Validation subdomains).

## Inputs

- HTTP/3 server deployment posture (TLS per RFC 9001, supported versions per RFC 9000 § 7.1).
- QPACK dynamic table sizing and block-stalling behaviour (RFC 9204).
- HTTP/3 priorities (RFC 9218: urgency, incremental) — surface to application or rely on framework defaults.
- 0-RTT usage per RFC 9000 / RFC 8470 — typically disabled or scoped to safe methods over HTTP/3.
- Origin validation posture (RFC 9527 ORIGIN frame, RFC 9460 SVCB / HTTPS RR alignment).

## ORCHORDS Profile

This guide is used as a reference when reviewing HTTP/3 deployment documentation or designing QUIC-based origin / edge infrastructure. It does NOT introduce protocol behaviour beyond what the RFCs and IANA registries specify. When a behavioural rule that is not captured here is required by an HTTP/3 operation, escalate to a fresh review against the current RFC and the relevant IANA registry.

## Implementation Notes

- HTTP/3 inherits HTTP semantics from RFC 9110 but carries them over QUIC, not TCP; reuse existing HTTP/1.1 or HTTP/2 logic in the application layer where feasible.
- Always combine HTTP/3 with RFC 9001 (TLS 1.3 in QUIC); disable TLS 1.2 or earlier over QUIC per RFC 9325.
- For 0-RTT, restrict to idempotent methods per RFC 8471 and align with QPACK stream state retention.
- Surface RFC 9218 priorities only where they deliver end-to-end benefit (e.g., when running over QUIC paths with mixed bandwidth); avoid static urgency assignments that defeat their value.
- For origin discovery, publish SVCB / HTTPS RR per RFC 9460 with the `h3` alpn; pair with the ORIGIN frame (RFC 9527) for subdomains sharing the same HTTP/3 endpoint.
- Pair with RFC 9221 (Bootstrapping WebSockets over HTTP/3) where WebSocket uplift is required.

## Companion Documents

- RFC 9000 (QUIC)
- RFC 9001 (QUIC + TLS 1.3)
- RFC 9002 (QUIC Loss Detection / Congestion Control)
- RFC 9204 (QPACK)
- RFC 9218 (HTTP Priorities)
- RFC 9221 (Bootstrapping WebSockets over HTTP/3)
- RFC 9298 (CONNECT-UDP)
- RFC 9474 (RTP over QUIC)
- RFC 9527 (HTTP/3 ORIGIN Frame)
- IANA HTTP/3 Settings / Error Codes / Frame Types registries
