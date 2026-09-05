---
title: "TLS 1.3 Protocol Version Guide (RFC 8446)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 8446; https://www.rfc-editor.org/rfc/rfc8446"
---

# TLS 1.3 Protocol Version Guide (RFC 8446)

## Scope

Reference card for Transport Layer Security version 1.3 (TLS 1.3) as defined in IETF RFC 8446, and selected updates including RFC 9155 (TLS 1.3 deprecation of older versions), RFC 8879 (Certificate Transparency), RFC 9325 (TLS recommendations), and RFC 5746 (renegotiation). Used by security, platform, and API teams when documenting cryptographic protocol selection, cipher suites, and certificate validation.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 8446, "The Transport Layer Security (TLS) Protocol Version 1.3" |
| Status | Standards Track, Proposed Standard |
| Obsoletes (in part) | RFC 5077, RFC 5246, RFC 6961 |
| Updates (selected) | RFC 9155 (version intolerance), RFC 9325 (recommendations) |
| Cipher suites (mandatory) | TLS_AES_128_GCM_SHA256, TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256 |
| Key exchange | (EC)DHE only; RSA key exchange removed |
| Authentication | Certificate, PSK (RFC 8446 §4.2), PSK with (EC)DHE |
| Extensions | server_name (SNI), supported_versions, supported_groups (RFC 7919), signature_algorithms, application_settings (ALPN RFC 7301), key_share, psk_key_exchange_modes, early_data (0-RTT), cookie |
| Handshake modes | Full 1-RTT, 0-RTT (early data), PSK resumption |
| Verification source | https://www.rfc-editor.org/rfc/rfc8446 and successor RFCs; IANA TLS parameters registry |

## Plan

1. Identify the deployment context (web/API, internal mTLS, IoT, VPN, QUIC).
2. Select the cipher suite family per RFC 9325 guidance and operator policy.
3. Plan certificate validation: chain validation, certificate transparency (RFC 9162, RFC 9578), OCSP stapling (RFC 6066), CRL access.
4. Decide on 0-RTT (early data): use only with replay-protection mechanisms.
5. Document version intolerance handling (RFC 9155) and fallback to TLS 1.2 only where mandated by interoperability requirements.

## Inputs

- Certificate and key material (chain, trust anchors, OCSP/CRL endpoints).
- Server-side configuration (cipher suite order, ALPN list, supported groups).
- Client-side policy (minimum TLS version, OCSP requirements, certificate pinning).
- Logging plan (handshake metadata, ja4 / SSLKEYLOG for incident response where permitted).

## ORCHORDS Profile

This guide is used as a reference for TLS documentation and protocol review. It does NOT introduce protocol behavior beyond what RFCs specify. When an operational requirement exceeds what is captured here, escalate to a fresh RFC review and the IANA TLS parameters registry.

## Implementation Notes

- TLS 1.3 requires (EC)DHE for forward secrecy; static RSA key exchange is removed.
- 0-RTT (early data) carries replay risk and is suitable only for idempotent requests.
- Mandatory cipher suites are listed in RFC 8446 §9.1; implementations must include all three.
- ALPN (RFC 7301) is required to negotiate application protocols (e.g., h2, http/1.1) over TLS.
- Certificate Transparency (RFC 9162, RFC 9578) requirements depend on the trust ecosystem (e.g., browser CT policy).

## Companion Documents

- RFC 9325 (TLS recommendations)
- RFC 9155 (version intolerance)
- RFC 7301 (ALPN)
- RFC 7919 (supported groups)
- RFC 9162 / RFC 9578 (Certificate Transparency)
- IANA TLS parameters registry
