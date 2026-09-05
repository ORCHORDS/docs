---
title: "Extensible Authentication Protocol (EAP) Version Guide (RFC 3748)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 3748 and selected EAP method RFCs; https://www.rfc-editor.org/rfc/rfc3748"
---

# Extensible Authentication Protocol (EAP) Version Guide (RFC 3748)

## Scope

Reference card for the Extensible Authentication Protocol (EAP) framework as defined in RFC 3748, used in IEEE 802.1X, IKEv2 (RFC 7296), PPPoE, and other link-layer or tunnel authentications. Used by network, security, and identity teams when documenting EAP method selection, AAA integration, and posture assessment for network access.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 3748, "Extensible Authentication Protocol (EAP)" |
| Status | Standards Track, Proposed Standard |
| Obsoletes | RFC 2284 |
| Selected method RFCs | RFC 4186 (EAP-PSK), RFC 4187 (EAP-AKA), RFC 5448 (EAP-AKA'), RFC 4187 updates, RFC 3748bis drafts, RFC 5216 (EAP-TLS), RFC 5281 (EAP-OTP), RFC 5247 (EAP key management framework), RFC 5996 (IKEv2 carrying EAP), RFC 6677 (channel binding), RFC 7055 (EAP-GPSK), RFC 7170 (TEAP), RFC 7268 (EAP-pwd), RFC 9428 (EAP-TEAP updates) |
| Selected types | EAP-TLS (13), EAP-TTLS (21), EAP-PEAP (25), EAP-FAST (43), EAP-SIM (18), EAP-AKA (23), EAP-AKA' (50), EAP-pwd (52), EAP-GPSK (51), EAP-TLS 1.3 (draft) |
| Verification source | https://www.rfc-editor.org/rfc/rfc3748 and successor RFCs; IANA EAP Numbers registry |

## Plan

1. Identify the access context (Wi-Fi 802.11, wired 802.1X, VPN/IKEv2, PPPoE).
2. Choose the EAP method based on credential type, key derivation requirements, and channel binding needs.
3. Map the chosen method to the AAA backend (RADIUS RFC 2865, RFC 3579, RFC 5176, and Diameter RFC 6733).
4. Validate mutual authentication, key derivation, and channel binding (RFC 6677) per deployment SLO.
5. Document certificate trust anchors and revocation checking.

## Inputs

- Network access policy (SSID, switch port profile, IKEv2 transform set).
- Credential type (certificate, SIM/AKA, PSK, OTP, secure password).
- AAA infrastructure (RADIUS server, Diameter agent) and required attributes.
- PKI trust anchor and OCSP/CRL access policy.

## ORCHORDS Profile

This guide is used as a reference for EAP method documentation and access-control design. It does NOT introduce protocol behavior beyond what RFCs specify. When an operational requirement exceeds what is captured here, escalate to a fresh RFC review and the IANA EAP Numbers / Method Types registries.

## Implementation Notes

- RFC 3748 defines the EAP framework; specific behavior is defined by individual method RFCs (for example, RFC 5216 for EAP-TLS).
- Mutual authentication is required; methods that do not derive a session key (e.g., EAP-MD5) are not appropriate for wireless access.
- Channel binding (RFC 6677) is recommended to detect man-in-the-middle attacks on tunneled EAP methods.
- Inner and outer identity handling: avoid disclosing user identifiers in clear text.
- Use RFC 5247 key management framework to verify key strength and freshness.

## Companion Documents

- RFC 2865 / RFC 3579 / RFC 5176 (RADIUS)
- RFC 6733 (Diameter)
- RFC 5247 (EAP key management framework)
- IANA EAP Numbers / Method Types registry
