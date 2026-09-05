---
title: "RADIUS Version Governance (RFC 2865)"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 2865; https://www.rfc-editor.org/rfc/rfc2865"
---

# RADIUS Version Governance (RFC 2865)

## Scope

Reference card for the Remote Authentication Dial-In User Service protocol as defined by IETF RFC 2865. Used by network, security, and operations teams when documenting AAA / 802.1X / VPN posture policy, RADIUS server and proxy deployment, or attribute handling. Treats RFC 2865 as the authoritative authentication / authorisation / accounting protocol, with RFC 2866 (RADIUS Accounting), RFC 2867 (Tunnel Support), RFC 2868 (CHANnel), RFC 2869 (Extensions), RFC 3579 (RADIUS Support for EAP), RFC 3580 (802.1X RADIUS), RFC 4668 (RADIUS Attributes), RFC 5176 (CoA / Disconnect), RFC 5580 (Location / State / Class / Vendor-Specific), RFC 6218 (PSK / passphrase), RFC 6613 (RADIUS/TLS), RFC 6614 (RADIUS/DTLS), RFC 6929 (IPv6 / IPv6-Prefix), RFC 7268 (RADIUS over DTLS profile), RFC 8044 (TLS-PSK for RADIUS/TLS), RFC 8559 (CoA DNS RR), RFC 8749 (Dynamic Peer Discovery), RFC 9440 (DEFLATE / TCP-AO), RFC 9780 (TLS Encryption of RADIUS), and RFC 9787 (Cipher-Suite Negotiation for RADIUS/TLS) as companion documents.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | RFC 2865, "Remote Authentication Dial-In User Service (RADIUS)" |
| Status | Draft Standard |
| Accounting | RFC 2866 |
| Tunneling | RFC 2867 |
| EAP support | RFC 3579, RFC 5447 |
| Encryption transports | RFC 6613 (RADIUS/TLS), RFC 6614 (RADIUS/DTLS), RFC 7268 (RADIUS/DTLS profile), RFC 9780 (TLS profiles), RFC 9787 (cipher negotiation) |
| Verification source | https://www.rfc-editor.org/rfc/rfc2865 and IANA RADIUS registries |

## Plan

1. Identify the deployment context (NAS / 802.1X authenticator, VPN concentrator, RADIUS server, RADIUS proxy, RADIUS/TLS- or DTLS-enabled edge).
2. Map required behaviour against RFC 2865 § 3–§ 5 (packet format, operation, considerations) and align with RFC 3579 / RFC 5176 for EAP and CoA.
3. Capture operational requirements: shared-secret policy (RFC 2865 § 3 + RFC 6218 PSK), transport encryption (RFC 6613 / RFC 6614), Change of Authorization (RFC 5176), and dynamic peer discovery (RFC 8749).
4. Validate against the live IANA registries (RADIUS Attribute Types, RADIUS Vendor-Specific Attribute IDs, RADIUS Codes, RADIUS Application IDs, RADIUS Crypto Suites, and the AAA DNS Resource Record Types per RFC 8559 / RFC 8749).

## Inputs

- Authentication posture (PAP / CHAP / MS-CHAP / EAP method list per RFC 3579).
- Authorisation attribute policy (Filter-Id, Tunnel attributes per RFC 2868 / RFC 2867 / RFC 4675 / RFC 5580).
- Accounting cadence (RFC 2866 interim updates, accounting on/off).
- Transport encryption posture (RADIUS/TLS or RADIUS/DTLS per RFC 6613 / RFC 6614 with cipher suite profile per RFC 9787).
- CoA policy (RFC 5176; source IP allow-list, RADIUS/DTLS mutual auth).

## ORCHORDS Profile

This guide is used as a reference when reviewing AAA / 802.1X / VPN documentation or designing RADIUS infrastructure. It does NOT introduce protocol behaviour beyond what the RFCs and IANA registries specify. When a behavioural rule that is not captured here is required by a RADIUS operation, escalate to a fresh review against the current RFC and the relevant IANA registry.

## Implementation Notes

- Always treat shared secrets as per-RFC 2865 § 3 (high-entropy, rotated) and prefer pre-shared keys per RFC 6218 in new deployments; never rely on plaintext PAP over an unencrypted RADIUS path.
- Use RADIUS/TLS (RFC 6613) or RADIUS/DTLS (RFC 6614) for transport-layer encryption; align cipher suite with RFC 9787 and disable legacy PSK-TLS where appropriate.
- Use RADIUS/DTLS (RFC 6614) over UDP for NAT traversal; use RADIUS/TLS (RFC 6613) over TCP where NAT is not in path; both with mutual authentication (RFC 9780 § 6).
- For NAS / 802.1X, align RFC 3580 attributes with RFC 4675 / RFC 5580 vendor-specific and standard attributes; confirm EAP method list against RFC 3579 / RFC 5447.
- Use DNS-based dynamic peer discovery (RFC 8559 / RFC 8749) only when DNS is trustworthy and DNSSEC-validating.

## Companion Documents

- RFC 2866 (RADIUS Accounting)
- RFC 2868 (CHANnel Attributes)
- RFC 2869 (Extensions)
- RFC 3162 (IPv6)
- RFC 3579 (EAP)
- RFC 3580 (802.1X)
- RFC 4668 / RFC 4675 / RFC 5580 (Attribute Profiles)
- RFC 5176 (CoA)
- RFC 6218 (PSK / passphrase)
- RFC 6613 / RFC 6614 / RFC 7268 / RFC 8044 / RFC 8559 / RFC 8749 / RFC 9440 / RFC 9780 / RFC 9787
- IANA RADIUS Attribute Types / Vendor IDs / Codes / Application IDs / Crypto Suites / DNS RR types
