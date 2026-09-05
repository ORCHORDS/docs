---
title: ETSI EN 303 645 Consumer IoT Cybersecurity Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ETSI EN 303 645 V2.1.1 (2020-12) — "Cyber Security for Consumer Internet of Things: Baseline Requirements"; https://www.etsi.org/deliver/etsi_en/303600_303699/303645/
---

# ETSI EN 303 645 Consumer IoT Cybersecurity Governance

## Scope

This card governs how `orchords-docs` evaluates consumer IoT products and reference architectures against ETSI EN 303 645 V2.1.1. It is the reference input for any KB card that cites consumer-grade IoT devices (smart speakers, IP cameras, wearables, connected appliances).

## Why this card exists

ETSI EN 303 645 is the baseline cybersecurity standard for consumer IoT products. It enumerates 13 mandatory and 5 recommended provisions that map onto the most common attack surface. Without an explicit card, KB consumer-IoT references drift from the published baseline.

## Document set

- **ETSI EN 303 645 V2.1.1** — Base cybersecurity requirements for consumer IoT.
- **ETSI TS 103 701** — Implementation of the EN 303 645 provisions.
- **ETSI TS 103 821** — Conformance assessment.
- **UK PSTI Act 2022** — UK implementation (Product Security and Telecommunications Infrastructure Act).
- **EU Cyber Resilience Act** — EU implementation (Regulation (EU) 2024/2847).

References: `https://www.etsi.org/deliver/etsi_en/303600_303699/303645/`.

## The 13 mandatory provisions

| # | Provision |
|---|---|
| 1 | No universal default passwords |
| 2 | Implement a vulnerability disclosure policy |
| 3 | Keep software updated |
| 4 | Securely store sensitive parameters |
| 5 | Communicate securely |
| 6 | Minimize exposed attack surfaces |
| 7 | Ensure software integrity |
| 8 | Ensure that personal data is secure |
| 9 | Make systems resilient to outages |
| 10 | Examine system telemetry data |
| 11 | Make it easy for users to delete user data |
| 12 | Make installation and maintenance of devices easy |
| 13 | Validate input data |

References: ETSI EN 303 645 V2.1.1 § 5.2-5.15.

## The 5 recommended provisions

| # | Provision |
|---|---|
| 14 | Keep software updated (recommended guidance) |
| 15 | Provide clean software provenance |
| 16 | Comply with consumer-IoT security best practices (further work) |
| 17 | Adopt product-resilience practices |
| 18 | Apply defense-in-depth |

References: ETSI EN 303 645 V2.1.1 § 5.16-5.20.

## Provision-by-provision binding

### Provision 1 — No universal default passwords

- Devices must be shipped with a unique password per device, OR require the user to set a unique password at first use.
- Pre-installed passwords must be device-specific and non-guessable.

### Provision 2 — Implement a vulnerability disclosure policy

- Manufacturer must publish a vulnerability disclosure policy.
- Policy must include a contact mechanism, an SLA, and a coordinated disclosure process.

### Provision 3 — Keep software updated

- Manufacturer must publish a security update policy.
- Update policy must specify the support window (≥ 5 years recommended).
- Updates must be authenticated and integrity-protected.

### Provision 4 — Securely store sensitive parameters

- Hard-coded credentials are forbidden.
- Security parameters (keys, certificates, secrets) must be stored in a secure element or protected storage.

### Provision 5 — Communicate securely

- All network communication must use best-practice cryptography (TLS 1.2+, DTLS 1.2+, OSCORE).
- No unencrypted credentials over the network.

### Provision 6 — Minimize exposed attack surfaces

- Disable unused services, ports, network listeners.
- Disable debug interfaces in production.

### Provision 7 — Ensure software integrity

- Software must be signed; signatures must be validated at boot.
- Boot integrity: Secure Boot.

### Provision 8 — Ensure personal data is secure

- Data minimization, purpose-of-use, lawful basis per ISO/IEC 27701.

### Provision 9 — Make systems resilient to outages

- Devices must remain functional during network outages (graceful degradation).
- Devices must not become a hazard when network is unreachable.

### Provision 10 — Examine system telemetry data

- Devices must log security-relevant events.
- Logs must be exported to a security monitoring system.

### Provision 11 — Make it easy for users to delete user data

- User-initiated reset must erase all user data.
- Reset procedure must be ≤ 5 minutes of user action.

### Provision 12 — Make installation and maintenance easy

- Setup procedure ≤ 10 minutes.
- Documentation covers setup, maintenance, decommission.

### Provision 13 — Validate input data

- Input validation at every entry point.
- No command injection, no buffer overflow, no path traversal.

## Recommended provisions — expanded

### Provision 14 (recommended) — Update policy

- Documented update frequency.
- Critical security update SLA: ≤ 7 days.

### Provision 15 (recommended) — Software provenance

- Software Bill of Materials (SBOM) per NTIA 2021.
- SBOM in SPDX or CycloneDX format.

### Provision 16 (recommended) — Best-practice conformance

- Code reviews, secure coding standards (CERT C, CERT C++, OWASP).

### Provision 17 (recommended) — Product resilience

- Defense-in-depth (network, application, data).
- Fail-secure defaults.

### Provision 18 (recommended) — Defense in depth

- Layered controls: network segmentation + device hardening + monitoring.

## Mandatory pre-flight (before adopting a consumer IoT device in a reference card)

1. The device is conformant to ETSI EN 303 645 V2.1.1.
2. The vendor publishes a vulnerability disclosure policy.
3. The vendor publishes a security update policy.
4. The device supports secure boot and signed firmware.
5. The vendor commits to the support window.
6. The device does not have hard-coded credentials.

## Cross-reference

| Domain | Card |
|---|---|
| Cryptography | ISO/IEC 27402, NIST SSDF |
| Vulnerability disclosure | ISO/IEC 30111, NIST CSWP |
| Data protection | ISO/IEC 27701, GDPR |
| Update mechanism | NIST SSDF, LwM2M Firmware Update |

## Self-attestation cycle

Every 180 days:

1. Walk every consumer IoT reference card.
2. Confirm ETSI EN 303 645 conformance is documented.
3. Update the next-review date.

## Sources

- ETSI EN 303 645 V2.1.1: `https://www.etsi.org/deliver/etsi_en/303600_303699/303645/`
- ETSI TS 103 701: `https://www.etsi.org/deliver/etsi_ts/103700_103799/103701/`
- UK PSTI Act 2022: `https://www.legislation.gov.uk/ukpga/2022/46/contents`
- EU Cyber Resilience Act: `https://eur-lex.europa.eu/eli/reg/2024/2847/oj`
- NTIA SBOM: `https://www.ntia.gov/sbom`
