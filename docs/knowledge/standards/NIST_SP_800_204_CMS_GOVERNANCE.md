---
title: NIST SP 800-204D Microservices Security Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST SP 800-204A (December 2019) — Building Secure Microservices-based Applications; NIST SP 800-204B (April 2022) — Attribute-based Access Control for Microservices-based Applications; NIST SP 800-204C (October 2022) — Implementation of DevSecOps for a Microservices-based Application; NIST SP 800-204D (April 2024) — Microservices-based Application Security; https://csrc.nist.gov/publications/detail/sp/800-204a/final
---

# NIST SP 800-204D Microservices Security Governance

## Scope

This card governs how `orchords-docs` evaluates microservices-based application security against the NIST SP 800-204 series. It is the reference input for any KB card that cites microservices, containerized applications, or cloud-native architectures.

## Why this card exists

NIST SP 800-204 is the canonical reference for microservices security in the US government. The series covers DevSecOps, ABAC, and operational security for microservices-based applications. Without an explicit card, the KB cites microservices patterns that do not survive a NIST-aligned audit.

## Document set

- **NIST SP 800-204A** — Building Secure Microservices-based Applications (December 2019).
- **NIST SP 800-204B** — Attribute-based Access Control for Microservices-based Applications (April 2022).
- **NIST SP 800-204C** — Implementation of DevSecOps for a Microservices-based Application (October 2022).
- **NIST SP 800-204D** — Microservices-based Application Security (April 2024).
- **NIST SP 800-204E** (in development) — Security Strategies for Microservice API Gateways.

References: `https://csrc.nist.gov/publications/detail/sp/800-204a/final`.

## Microservices architecture tenets

Per SP 800-204A:

| Tenet | Description |
|---|---|
| Single Responsibility | each microservice owns a single bounded context |
| Independent Deployment | each microservice deploys independently |
| Decentralized Data | each microservice owns its own data |
| Polyglot | each microservice can use a different stack |
| Failure Isolation | failure in one microservice does not cascade |
| Observable | every microservice is observable end-to-end |
| API-driven | every microservice exposes a well-defined API |

## Security controls

### Identity and authentication

- mTLS at every service-to-service boundary.
- Workload identity (SPIFFE / SPIRE).
- Identity-aware proxy at every ingress.

### Authorization

- ABAC per SP 800-204B.
- Policy Decision Point (PDP) at every call.
- Policy Enforcement Point (PEP) at every call.

### Data security

- Encryption at rest (CMK).
- Encryption in transit (TLS 1.3 / mTLS).
- Field-level encryption for sensitive fields.
- Tokenization / pseudonymization per `ISO_IEC_27701_2019_PIMS_GOVERNANCE.md`.

### API security

- API gateway with rate limiting, WAF, schema validation.
- OpenAPI / protobuf schema enforcement.
- API key / OAuth 2.0 / mTLS authentication per `OAUTH_2_1_VERSION_GOVERNANCE.md`.

### Container security

- Image scanning (Trivy, Grype, Clair).
- Runtime security (Falco, Tetragon, Cilium Tetragon).
- Admission control (OPA, Kyverno).

## DevSecOps (SP 800-204C)

- Source control with PR review.
- CI pipeline with security gates.
- CD pipeline with progressive delivery.
- Continuous monitoring.
- SBOM per `NIST_CSWP_23_2024_SSB_GOVERNANCE.md`.

## Mandatory pre-flight (before adopting a new microservices-based reference architecture)

1. Microservices tenets are documented.
2. mTLS is configured at every boundary.
3. ABAC is wired.
4. API gateway is configured.
5. Container security is wired.
6. SBOM is published.
7. Observability is wired.

## Cross-reference

| Domain | Card |
|---|---|
| Identity | `OIDC_VERSION_GOVERNANCE.md`, `WORKLOAD_IDENTITY_ROTATION_PLAYBOOK.md` |
| Service mesh | `SERVICE_MESH_MTLS_ROLLOUT_PLAYBOOK.md` |
| AI security | `ISO_IEC_27402_2024_AI_SECURITY_GOVERNANCE.md` |
| Zero Trust | `NIST_SP_800_207_ZERO_TRUST_GOVERNANCE.md` |
| Supply chain | `NIST_CSWP_23_2024_SSB_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every microservices reference card.
2. Confirm conformance to SP 800-204 series.
3. Confirm mTLS, ABAC, container security are wired.
4. Update the next-review date.

## Sources

- NIST SP 800-204A: `https://csrc.nist.gov/publications/detail/sp/800-204a/final`
- NIST SP 800-204B: `https://csrc.nist.gov/publications/detail/sp/800-204b/final`
- NIST SP 800-204C: `https://csrc.nist.gov/publications/detail/sp/800-204c/final`
- NIST SP 800-204D: `https://csrc.nist.gov/publications/detail/sp/800-204d/final`
- NIST SP 800-204 (parent landing page): `https://csrc.nist.gov/publications/sp800`
