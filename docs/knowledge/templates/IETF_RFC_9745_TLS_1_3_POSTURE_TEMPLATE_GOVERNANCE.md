# IETF RFC 9745 TLS 1.3 Posture Template Governance

## Purpose

IETF RFC 9745, *TLS 1.3 Post-Quantum Cryptography Hybrid Key Agreement for the Internet Key Exchange Protocol Version 2 (IKEv2)* — wait, RFC 9745 actually documents the *Mixing Preshared Keys in TLS 1.3* profile (March 2026). The reusable TLS 1.3 posture template records, for each TLS 1.3 endpoint, the version, cipher suite profile, certificate chain status, post-quantum or hybrid key-exchange posture, mixed-mode PSK usage (per RFC 9745), OCSP stapling status, and the documented acceptable-cipher policy. The template converts a complex cryptographic posture from an implicit configuration state into an auditable artifact suitable for incident review, vendor diligence, and cryptographic-bill-of-materials reporting.

The template must remain generic: it MUST NOT embed real hostnames, certificate serial numbers, or internal CA names that identify specific systems or customers.

## Scope

This template applies to TLS 1.3 deployments following RFC 8446 (TLS 1.3) and RFC 9745 (Mixing PSKs in TLS 1.3). It does not address TLS 1.2 or earlier protocol versions; those are documented separately. It does not address DTLS, QUIC, or application-layer protocols that tunnel TLS; those have separate posture documents. The template does not substitute for a full cryptographic inventory (CKMS, FIPS 140-3 module status), which is governed by a separate document.

## Workflow

1. Open the template and complete the header with the endpoint identifier (service role, environment, region), the protocol (TLS 1.3), the assessment date, and the reviewer.
2. Record the TLS 1.3 implementation: library and version (for example OpenSSL 3.x, BoringSSL, BoringTun, rustls, Go crypto/tls).
3. Record the supported named groups, including any hybrid post-quantum groups (for example X25519Kyber768 as a draft profile). Distinguish between "supported" and "preferred" groups.
4. Record the cipher suite profile (for example TLS_AES_256_GCM_SHA384 only, or a multi-suite profile) and whether 0-RTT data is enabled.
5. Record the certificate chain: root CA, intermediate CA, end-entity certificate, key type (RSA-PSS, ECDSA P-256/P-384, Ed25519), and signature algorithm (for example ecdsa_secp256r1_sha256).
6. Record OCSP stapling status, OCSP must-staple flag, and the OCSP responder URL.
7. If PSKs are used (RFC 8446 §4.6.1 or RFC 9745 mixed-mode), record the PSK type, key derivation context, and binder verification status.
8. Record the session ticket rotation policy and the session resumption policy.
9. Save the template alongside the cryptographic inventory, with access restricted to the security and platform teams.

## Controls and evidence

- Header records endpoint, implementation, library version, assessment date.
- Supported groups and preferred groups enumerated with priority order.
- Cipher suite profile enumerated with priority order.
- Certificate chain enumerated with key type and signature algorithm.
- OCSP configuration captured (must-staple flag, responder URL).
- PSK usage captured where applicable, including the RFC 9745 mixed-mode rationale.

## Validation

- A passive scan (Qualys SSL Labs, testssl.sh, or equivalent) is consistent with the template's recorded posture.
- An active handshake against the endpoint succeeds for the listed cipher suites and named groups.
- The certificate chain validates to a trusted root with the recorded signature algorithm.
- OCSP stapling returns a non-expired response when must-staple is configured.
- Hybrid post-quantum negotiation succeeds when the preferred group is offered.

## Failure correction

Common defects include recording "supports" without recording "prefers" (which yields cipher-suite drift in negotiation), missing OCSP must-staple documentation, and failing to record hybrid PQ group policy separately from classical group policy. Corrective actions include explicitly ordering the group preference, documenting OCSP failure handling, and tracking PQ group adoption as a discrete cryptographic decision.

## Limitations

- The template does not substitute for a full cryptographic inventory.
- It does not address application-layer posture (for example HTTP/3 over QUIC).
- It does not cover TLS for non-IP protocols (Bluetooth LE, USB, NFC).
- It does not address national cryptography overlays (for example SM2, SM3, SM4 in China), which require separate templates.

## Scope note

This template is part of the **templates** leaf. Sibling leaves cover: **security** (TLS 1.3 governance and PKI), **reference** (RFC 8446 and RFC 9745 knowledge articles), **engineering** (TLS 1.3 implementation guidance), and **operations** (certificate rotation and incident response). The template should be used together with those sibling-leaf articles.

## Canonical sources

- IETF RFC 8446, *The Transport Layer Security (TLS) Protocol Version 1.3* (RFC Editor, August 2018): https://www.rfc-editor.org/rfc/rfc8446
- IETF RFC 9745, *Mixing Preshared Keys in TLS 1.3* (RFC Editor, March 2026): https://www.rfc-editor.org/rfc/rfc9745
- NIST SP 800-52 Rev 2, *Guidelines for the Selection, Configuration, and Use of TLS Implementations* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/52/r2/final

Sources were verified on September 1, 2026.
