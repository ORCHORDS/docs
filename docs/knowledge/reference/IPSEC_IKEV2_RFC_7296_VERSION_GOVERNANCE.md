---
title: "IPsec / IKEv2 (RFC 7296) Version Governance"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "IETF RFC 7296 (October 2014); RFC 4303 (IPsec ESP, December 2005); RFC 4301 (IPsec Architecture, December 2005); https://www.rfc-editor.org/rfc/rfc7296"
---

# IPsec / IKEv2 (RFC 7296) Version Governance

## Purpose

This card governs how ORCHORDS references the Internet Protocol Security (IPsec) suite and the Internet Key Exchange version 2 (IKEv2) protocol. IPsec provides confidentiality, integrity, authentication, and anti-replay for traffic at the network layer; IKEv2 negotiates and refreshes the keys and Security Associations (SAs) that protect that traffic.

## Canonical Reference

- IETF RFC 7296 — *Internet Key Exchange Protocol Version 2 (IKEv2)*, October 2014 (obsoletes RFC 5996; updates RFC 4306).
- IETF RFC 4303 — *IP Encapsulating Security Payload (ESP)*, December 2005.
- IETF RFC 4301 — *Security Architecture for the Internet Protocol*, December 2005.
- IETF RFC 4302 — *IP Authentication Header (AH)*, December 2005 (rarely used; ESP+NULL is preferred for most modern deployments).
- Companion: RFC 6379 (Suite B Cryptographic Suites), RFC 8420 (IKEv2 fragmentation), RFC 8784 (post-quantum pre-shared keys for IKEv2).

## Core Properties

- **Two-protocol structure** — IKEv2 (UDP port 500/4500) negotiates SAs and authenticates peers; ESP (IP protocol 50) or, less commonly, AH (protocol 51) protects the traffic itself.
- **IKEv2 exchanges** — `IKE_SA_INIT` (two messages, Diffie-Hellman, nonces, SA proposal) and `IKE_AUTH` (two messages, identity, authentication). Subsequent `CREATE_CHILD_SA` exchanges re-key or add child SAs.
- **Authentication methods** — Pre-shared keys, RSA/ECDSA certificates, EAP (RFC 5998), and PQC pre-shared keys (RFC 8784 / RFC 9370).
- **Anti-replay** — 32-bit or 64-bit Sequence Number (ESN) on ESP; IKEv2 itself uses Message ID + Windowing (RFC 7296 §2.2).
- **Mobility** — MOBIKE (RFC 4555) lets a peer change its address mid-session without tearing down the SA.
- **Dead Peer Detection (DPD)** — RFC 7296 §2.4 defines `INFORMATIONAL` exchanges with no payloads as liveness probes.
- **NAT traversal** — RFC 7296 §2.23 and RFC 3948 encapsulate ESP inside UDP port 4500 when NAT is detected.
- **Hash/Integrity negotiation** — HMAC-SHA-256, HMAC-SHA-384, HMAC-SHA-512; SHA-1 retained only for backward compatibility and disallowed for new deployments.
- **Encryption negotiation** — AES-CBC (legacy), AES-GCM (preferred; AEAD), ChaCha20-Poly1305 (RFC 7634), AES-CCM, AES-GCM-256.

## Migration and Version Drift

| IPsec feature | Status | Notes |
| --- | --- | --- |
| IKEv1 (RFC 2409) | Deprecated | Removed from most modern stacks; Cisco IOS-XE deprecated IKEv1 in 17.x. Use IKEv2 for new deployments. |
| AH (RFC 4302) | Legacy | Replaced by ESP with NULL encryption + integrity. |
| 3DES-CBC | Disallowed | Per NIST SP 800-131A Rev. 2 (March 2024) and RFC 8247. |
| AES-CBC + HMAC-SHA-1 | Acceptable for legacy interop only | New deployments should use AES-GCM-128/256 or ChaCha20-Poly1305. |
| AES-GCM-16 (AEAD) | Preferred | Single algorithm provides both confidentiality and integrity. |
| IKEv2 fragmentation (RFC 8019) | Recommended | Required for any deployment with intermediate NAT or MTU less than ~1280. |
| Post-quantum pre-shared keys (RFC 8784) | Recommended for high-assurance | Hybrid PQ key exchange via RFC 9370 in IKEv2. |
| IKEv2 with ECDSA / EdDSA | Preferred | Smaller certificates, faster handshakes; RFC 8420 only needed when fragmented or large. |

## Usage in ORCHORDS

- Use IKEv2 with AES-GCM-16 or ChaCha20-Poly1305 for site-to-site and remote-access VPNs.
- For cloud-to-cloud links, prefer IKEv2 with ECDSA P-256/P-384 and PFS enabled (separate DH per rekey).
- Avoid IKEv1 unless connecting to a peer that does not support IKEv2.
- Treat any new RFC 8784 / RFC 9370 PQ-hybrid profile as a project deliverable, not a deployment default, until the IPsec vendor landscape converges.

## Open Items

- Track IETF IPSECME working group output on additional AEAD transforms and additional DH groups.
- Watch for RFC 9370 (Hybrid PQ) implementations in major IPsec stacks (strongSwan, libreswan, OpenSwan, vendor SDKs).
- Re-evaluate MOBIKE in environments where QUIC/IP-layer roaming (RFC 9312) is also available.
