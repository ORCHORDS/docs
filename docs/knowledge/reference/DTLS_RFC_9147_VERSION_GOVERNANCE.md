---
title: "DTLS 1.3 Protocol Version Guide (RFC 9147)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 9147 (May 2022); https://www.rfc-editor.org/rfc/rfc9147"
---

# DTLS 1.3 Protocol Version Guide (RFC 9147)

## Scope

Reference card for Datagram Transport Layer Security version 1.3 (DTLS 1.3) as specified in IETF RFC 9147 (May 2022). Used by VPN, IoT, VoIP, real-time media, and constrained-channel teams when documenting datagram-authenticated session design. Treats RFC 9147 as the baseline and RFCs 6347 (DTLS 1.2) and 8093 (large record sizes) as selected predecessors.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 9147, "The Datagram Transport Layer Security (DTLS) Protocol Version 1.3" |
| Status | Proposed Standard |
| Obsoletes | RFC 6347 (DTLS 1.2) when used with the TLS 1.3 record layer (RFC 8446) |
| Companion | RFC 8446 (TLS 1.3), RFC 6347 (DTLS 1.2), RFC 8093 (large record sizes for IoT) |
| Record layer | Reuses TLS 1.3 record layer with explicit epoch-free record protection |
| Replay defense | Sequence-number window or sliding window per section 4.1.2 |
| Cipher suites (selected) | TLS_AES_128_GCM_SHA256, TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256 |
| Verification source | https://www.rfc-editor.org/rfc/rfc9147 |

## Plan

1. Identify the deployment context (VPN tunnel, IoT datagram control, real-time media, constrained network).
2. Map required features against RFC 9147 datagram adaptations of TLS 1.3 (handshake message retransmission, record replay window, large record sizes per RFC 8093 where applicable).
3. Capture the operational requirements: UDP transport, MTU sizing, anti-amplification limits, key export limits, and congestion-aware retransmission.
4. Validate against the live IANA registry of DTLS-related parameters and your operator policy.

## Inputs

- Datagram transport specification (UDP port, MTU, congestion control).
- Required cipher suites and extensions (supported_versions, supported_groups, signature_algorithms, psk_key_exchange_modes, cookie).
- Replay window size and timeout behavior.
- Operational policy (session resumption, ticket lifetime, key export, observable errors).

## ORCHORDS Profile

This guide is used as a reference when reviewing datagram session design or peer configuration. It does NOT introduce protocol behavior beyond what RFC 9147 specifies. When a datagram operation requires a behavioral rule that is not captured here, escalate to a fresh review against the current RFC.

## Implementation Notes

- DTLS 1.3 reuses the TLS 1.3 handshake with datagram adaptations for retransmission and reorder tolerance; do not configure it as a TCP-only TLS 1.3 stack.
- Anti-amplification: a DTLS server MUST NOT respond with more bytes than the client offered; enforce on edge devices.
- Replay window: configure per RFC 9147 section 4.1.2 (default 64 packets is typical; verify against the implementation).
- Cookie extension is mandatory in many deployments to prevent DoS amplification; verify the implementation supports it.
- For IoT scenarios, RFC 8093 large record sizes may be enabled; pair with MTU/path MTU verification.
- Datagram applications that mix DTLS with QUIC should be aware that QUIC integrates TLS 1.3 directly (RFC 9001) and is the preferred transport for new designs.

## Companion Documents

- RFC 8446 (TLS 1.3)
- RFC 6347 (DTLS 1.2 — predecessor)
- RFC 8093 (large DTLS record sizes)
- RFC 9001 (QUIC uses TLS 1.3)
- IANA TLS Cipher Suites registry
