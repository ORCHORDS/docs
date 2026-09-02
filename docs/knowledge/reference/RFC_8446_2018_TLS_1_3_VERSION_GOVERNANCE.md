# IETF RFC 8446:2018 TLS 1.3 Protocol Governance

## Purpose

IETF RFC 8446, "The Transport Layer Security (TLS) Protocol Version 1.3," defines the TLS 1.3 protocol. TLS 1.3 provides improved security and performance compared to TLS 1.2: it removes legacy cipher suites, mandates forward secrecy, reduces the handshake to one round trip (or zero round trips with 0-RTT data), and encrypts more of the handshake. This article governs the application of RFC 8446 so TLS 1.3 deployments follow the standard's structure.

## Scope

The specification applies to TLS 1.3 deployments. Within this knowledge base, the article covers the TLS 1.3 handshake, the supported cipher suites, the supported groups (curves), the supported signature algorithms, the application-layer protocol negotiation (ALPN), 0-RTT data and its replay risks, and the documentation of the TLS configuration. It does not cover DTLS 1.3 (a separate specification).

## Workflow

1. Establish the TLS 1.3 policy: scope, supported cipher suites (AEAD only — TLS 1.3 mandates AEAD), supported groups, supported signature algorithms, ALPN protocols, and 0-RTT use cases.
2. Configure the TLS 1.3 deployment:
   - Cipher suites: TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256, TLS_AES_128_GCM_SHA256. Limit to the policy-approved suites.
   - Supported groups: X25519, P-256, P-384. Limit to the policy-approved groups.
   - Signature algorithms: RSA-PSS, ECDSA, Ed25519, Ed448. Limit to the policy-approved algorithms.
   - ALPN: negotiate the application protocol (h2, http/1.1).
   - 0-RTT data: enable only for idempotent operations (GETs); use single-use session tickets to limit replay.
3. Disable downgrade compatibility for non-TLS 1.3 clients where the policy allows.
4. Test the configuration against TLS scanners and the deployment's expected clients.
5. Document the configuration, the cipher suites, the supported groups, the signature algorithms, and the 0-RTT policy.

## Controls and evidence

TLS 1.3 controls include the documented configuration, the deployment configuration records, the test results, and the audit records. Each TLS endpoint should be reviewable against the policy.

## Validation

Validation should confirm only approved cipher suites, groups, and signature algorithms are enabled, the downgrade compatibility settings match the policy, the ALPN negotiation works as expected, and 0-RTT is used only where the policy permits. Periodic scans confirm the configuration remains aligned.

## Failure correction

Common failure modes: 0-RTT is enabled for non-idempotent operations (correct: limit 0-RTT to idempotent operations or disable it); downgrade compatibility is enabled beyond policy (correct: configure downgrade compatibility per policy); unsupported groups are accepted (correct: limit to the policy-approved groups); the configuration is not tested after changes (correct: test the configuration after each change).

## Limitations

RFC 8446 defines TLS 1.3; it does not certify any implementation. The standard does not address every use case (e.g., embedded devices with constrained resources may need RFC-aligned but smaller cipher suites). 0-RTT data has replay risks that the implementation must address per the policy.

## Scope note

This article summarizes project-neutral reference use of IETF RFC 8446. It does not assert any specific deployment's conformance or claim any certification outcome.

## Canonical sources

- IETF RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3: https://www.rfc-editor.org/rfc/rfc8446
- IETF RFC 8447 — IANA Registry Updates for TLS 1.3: https://www.rfc-editor.org/rfc/rfc8447