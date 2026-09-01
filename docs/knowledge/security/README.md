---
title: "Security Documentation"
owner: "Documentation Maintainer"
status: "approved"
classification: "public"
last-reviewed: "2026-08-26"
review-cycle: "90 days"
next-review: "2026-11-24"
---

# Security Documentation

This family contains reusable security engineering and assurance guidance. It covers application security, authentication, authorization, cloud security, cryptography, dependency security, identity and access, network security, secrets, software supply chain, threat modeling, vulnerability management, and web security.

## Selected current guidance

- [TLS Service Identity Verification with RFC 9525](engineering/tls-service-identity-verification-rfc-9525.md)
- [Coordinating System Security, Privacy, and C-SCRM Plans](SYSTEM_PLAN_SECURITY_PRIVACY_C_SCRM_COORDINATION.md)
- [Syncable Authenticator Governance](SYNCABLE_AUTHENTICATOR_GOVERNANCE.md)
- [Subscriber-Controlled Wallet Federation](SUBSCRIBER_CONTROLLED_WALLET_FEDERATION.md)
- [Remote Identity Proofing: Digital Injection and Forged-Media Defenses](REMOTE_IDENTITY_PROOFING_FORGED_MEDIA_DEFENSES.md)
- [Trusted Referee Identity-Proofing Exceptions](TRUSTED_REFEREE_IDENTITY_PROOFING_EXCEPTIONS.md)
- [Applicant Reference Identity-Proofing Governance](APPLICANT_REFERENCE_IDENTITY_PROOFING_GOVERNANCE.md)
- [Federation Attribute-Bundle Lifecycle](FEDERATION_ATTRIBUTE_BUNDLE_LIFECYCLE.md)
- [Federated Account Change Signaling](FEDERATED_ACCOUNT_CHANGE_SIGNALING.md)
- [Identity-Proofing Fraud Management](IDENTITY_PROOFING_FRAUD_MANAGEMENT.md)
- [NIST CSF 2.0 Incident Response Integration](NIST_CSF2_INCIDENT_RESPONSE_INTEGRATION.md)
- [CISA SCuBA Cloud Tenant Baseline Governance](CISA_SCUBA_CLOUD_TENANT_BASELINE_GOVERNANCE.md)
- [TLS and DTLS RFC 9325 Deployment Baseline](engineering/tls-dtls-rfc-9325-bcp195-deployment-baseline.md)

## 2026-09-01 standards and implementation guidance

- [Automated Certificate Management Environment (ACME) IP Identifier Validation Extension: Engineering and Governance](engineering/acme-ip-identifier-validation-rfc8738.md)
- [Automated Certificate Management Environment (ACME) TLS Application-Layer Protocol Negotiation (ALPN) Challenge Extension: Engineering and Governance](engineering/acme-tls-alpn-challenge-rfc8737.md)
- [Elliptic Curves for Security: Engineering and Governance](engineering/curve25519-curve448-interoperability-rfc7748.md)
- [CycloneDX VEX Analysis Governance](engineering/cyclonedx-vex-analysis-governance.md)
- [Deprecating TLS 1.0 and TLS 1.1 (RFC 8996)](engineering/deprecating-tls-1-0-and-tls-1-1-rfc-8996.md)
- [DNS over Dedicated QUIC Connections: Engineering and Governance](engineering/dns-over-quic-rfc9250.md)
- [Specification for DNS over Transport Layer Security (TLS): Engineering and Governance](engineering/dns-over-tls-rfc7858.md)
- [DNS Security Introduction and Requirements: Engineering and Governance](engineering/dnssec-introduction-requirements-rfc4033.md)
- [DNS Security (DNSSEC) Hashed Authenticated Denial of Existence: Engineering and Governance](engineering/dnssec-nsec3-authenticated-denial-rfc5155.md)
- [Protocol Modifications for the DNS Security Extensions: Engineering and Governance](engineering/dnssec-protocol-validation-rfc4035.md)
- [Resource Records for the DNS Security Extensions: Engineering and Governance](engineering/dnssec-resource-records-rfc4034.md)
- [Automated Updates of DNS Security (DNSSEC) Trust Anchors: Engineering and Governance](engineering/dnssec-trust-anchor-rollover-rfc5011.md)
- [Edwards-Curve Digital Signature Algorithm (EdDSA): Engineering and Governance](engineering/eddsa-rfc8032-interoperability.md)
- [Financial-grade API Part 2: Advanced Security Profile](engineering/fapi-1-advanced-profile.md)
- [Financial-grade API Part 1: Baseline Security Profile](engineering/fapi-1-baseline-profile.md)
- [FAPI 2.0 Attacker Model](engineering/fapi-2-attacker-model.md)
- [FAPI 2.0 Security Profile](engineering/fapi-2-security-profile.md)
- [GUAC Supply-Chain Graph Governance](engineering/guac-supply-chain-graph-governance.md)
- [HMAC-based Extract-and-Expand Key Derivation Function (HKDF): Engineering and Governance](engineering/hkdf-key-derivation-rfc5869.md)
- [in-toto Layout and Threshold Governance](engineering/in-toto-layout-threshold-governance.md)
- [JWK Thumbprint URI: Engineering and Governance](engineering/jwk-thumbprint-uri-rfc9278.md)
- [JWT Proof-of-Possession Confirmation (RFC 7800)](engineering/jwt-proof-of-possession-cnf-rfc-7800.md)
- [Transitioning the Use of Cryptographic Algorithms and Key Lengths: Engineering and Governance](engineering/nist-sp800-131a-r2-crypto-transition.md)
- [OAuth Assertion Framework (RFC 7521)](engineering/oauth-assertion-framework-rfc-7521.md)
- [OAuth 2.0 Grant Management for Authorization](engineering/oauth-grant-management-1-0.md)
- [JWT Secured Authorization Response Mode (JARM)](engineering/oauth-jarm-1-0.md)
- [JWT Bearer Assertions for OAuth (RFC 7523)](engineering/oauth-jwt-bearer-assertion-rfc-7523.md)
- [JWT Response for OAuth Token Introspection](engineering/oauth-jwt-introspection-response.md)
- [JWT-Secured Authorization Request (RFC 9101)](engineering/oauth-jwt-secured-authorization-request-rfc-9101.md)
- [SAML 2.0 Bearer Assertions for OAuth (RFC 7522)](engineering/oauth-saml2-bearer-assertion-rfc-7522.md)
- [OAuth Token Revocation (RFC 7009)](engineering/oauth-token-revocation-rfc-7009.md)
- [Online Certificate Status Protocol (OCSP) Nonce Extension: Engineering and Governance](engineering/ocsp-nonce-extension-rfc8954.md)
- [X.509 Internet Public Key Infrastructure Online Certificate Status Protocol - OCSP: Engineering and Governance](engineering/ocsp-status-protocol-rfc6960.md)
- [OpenID Connect CIBA Core 1.0](engineering/openid-connect-ciba-core-1-0.md)
- [OpenID Connect Discovery 1.0](engineering/openid-connect-discovery-1-0.md)
- [Initiating User Registration via OpenID Connect](engineering/openid-connect-prompt-create-1-0.md)
- [OpenID Connect RP-Initiated Logout 1.0](engineering/openid-connect-rp-initiated-logout-1-0.md)
- [OpenVEX Statement Lifecycle and Distribution](engineering/openvex-statement-lifecycle.md)
- [OWASP API Security API1:2023 BOLA Verification](engineering/owasp-api-bola-verification.md)
- [OWASP API Security API7:2023 SSRF Verification](engineering/owasp-api-ssrf-verification.md)
- [OWASP ASVS 5.0.0 File Handling Verification](engineering/owasp-asvs-file-handling.md)
- [OWASP ASVS 5.0.0 Level Selection](engineering/owasp-asvs-level-selection.md)
- [OWASP ASVS 5.0.0 Session Management Verification](engineering/owasp-asvs-session-verification.md)
- [OWASP MASTG 2.0 Authentication and Biometrics](engineering/owasp-mastg-authentication-biometric.md)
- [OWASP MASTG 2.0 Test Evidence](engineering/owasp-mastg-test-evidence.md)
- [OWASP MASVS 2.1 Network and Platform Verification](engineering/owasp-masvs-network-platform.md)
- [OWASP MASVS 2.1.0 Profile Selection](engineering/owasp-masvs-profile-selection.md)
- [OWASP MASVS 2.1 Storage and Privacy Verification](engineering/owasp-masvs-storage-privacy.md)
- [OWASP SAMM 2.0 Assessment](engineering/owasp-samm-assessment.md)
- [Rekor Inclusion and Transparency Monitoring](engineering/rekor-inclusion-monitoring.md)
- [PKCS #1: RSA Cryptography Specifications Version 2.2: Engineering and Governance](engineering/rsa-pkcs1-v22-rfc8017.md)
- [SCIM Core Schema (RFC 7643)](engineering/scim-core-schema-rfc-7643.md)
- [Security Event Token (RFC 8417)](engineering/security-event-token-rfc-8417.md)
- [Sigstore Bundle Retention and Offline Verification](engineering/sigstore-bundle-offline-verification.md)
- [Sigstore Keyless Signing Identity Policy](engineering/sigstore-keyless-identity-policy.md)
- [SLSA Build Track Level Adoption](engineering/slsa-build-track-level-adoption.md)
- [SLSA Source Track Governance](engineering/slsa-source-track-governance.md)
- [SPDX 3 Security Profile Adoption](engineering/spdx-3-security-profile-adoption.md)
- [Transport Layer Security (TLS) Application-Layer Protocol Negotiation Extension: Engineering and Governance](engineering/tls-alpn-negotiation-rfc7301.md)
- [X.509v3 Transport Layer Security (TLS) Feature Extension: Engineering and Governance](engineering/tls-feature-extension-rfc7633.md)
- [Internet X.509 Public Key Infrastructure Certificate and Certificate Revocation List (CRL) Profile: Engineering and Governance](engineering/x509-certificate-crl-profile-rfc5280.md)
