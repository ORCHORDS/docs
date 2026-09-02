# IETF RFC 8422:2018 TLS 1.2 Cipher Suites Governance

## Purpose

IETF RFC 8422 updates the TLS 1.2 cipher suite definitions for elliptic curve cryptography (ECC). The RFC defines the cipher suites using elliptic curve Diffie-Hellman (ECDH) for key exchange with TLS 1.2, and updates the supported curves and signature algorithms. This article governs the application of RFC 8422 in TLS 1.2 deployments, focusing on the ECC aspects of the cipher suite selection.

## Scope

The specification applies to TLS 1.2 deployments using elliptic curve cryptography. Within this knowledge base, the article covers the ECC cipher suites defined in RFC 8422, the supported curves (NIST P-256, P-384, P-521, brainpool curves), the signature algorithms (ECDSA, EdDSA), the relationship to the TLS 1.2 protocol (RFC 5246), and the documentation of the cipher suite selection. It does not cover TLS 1.3 (which is a separate specification, RFC 8446); readers should consult that for newer deployments.

## Workflow

1. Establish the TLS cipher suite policy: scope, supported cipher suites, supported curves, supported signature algorithms, and the relationship to the broader cryptography policy.
2. Identify the TLS 1.2 deployments in scope. For each deployment, identify the cipher suites currently enabled.
3. Apply the RFC 8422 ECC cipher suites:
   - ECDHE_ECDSA cipher suites for ephemeral ECDH with ECDSA-signed certificates.
   - ECDHE_RSA cipher suites for ephemeral ECDH with RSA-signed certificates.
   - ECDH_ECDSA and ECDH_RSA (non-ephemeral) cipher suites are available for legacy interop where appropriate.
4. Restrict the supported curves to the named curves the organization has approved (e.g., NIST P-256 and P-384; brainpool curves where required).
5. Restrict the signature algorithms to approved algorithms (ECDSA with approved curves, EdDSA with the Ed25519 or Ed448 curves).
6. Disable cipher suites that use deprecated algorithms (RC4, MD5, SHA-1 in signatures) or that do not provide forward secrecy (static RSA, static DH).
7. Document the supported cipher suites, the supported curves, the signature algorithms, and the rationale for each choice.

## Controls and evidence

Cipher suite controls include the documented configuration, the deployment configuration records, the test results confirming the cipher suites work as expected, and the audit records showing only approved suites are enabled. Each TLS endpoint should be reviewable against the configuration.

## Validation

Validation should confirm only approved cipher suites are enabled, the supported curves are limited to approved curves, the signature algorithms are limited to approved algorithms, the configuration matches the policy, and the test results support the configuration. Periodic scans confirm the configuration remains aligned.

## Failure correction

Common failure modes: deprecated cipher suites remain enabled (correct: disable suites using RC4, MD5, SHA-1, static RSA, or static DH); unsupported curves are accepted (correct: limit the supported curves to the policy); signature algorithms are weak (correct: use ECDSA with approved curves or EdDSA); the configuration is not tested after changes (correct: test the configuration against a TLS scanner after each change).

## Limitations

RFC 8422 updates the ECC aspects of TLS 1.2; it does not address the broader TLS protocol design. New deployments should prefer TLS 1.3 (RFC 8446) which provides better security properties by default. The RFC does not certify any implementation; readers should test against the IETF test vectors and against the implementation's documentation.

## Scope note

This article summarizes project-neutral reference use of IETF RFC 8422. It does not assert any specific deployment's conformance or claim any certification outcome.

## Canonical sources

- IETF RFC 8422 — Elliptic Curve Cryptography (ECC) Cipher Suites for Transport Layer Security (TLS) Versions 1.2 and Earlier: https://www.rfc-editor.org/rfc/rfc8422
- IETF RFC 5246 — The Transport Layer Security (TLS) Protocol Version 1.2 (superseded by RFC 8446): https://www.rfc-editor.org/rfc/rfc5246