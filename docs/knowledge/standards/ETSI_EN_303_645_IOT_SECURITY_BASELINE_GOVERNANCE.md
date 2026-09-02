# ETSI EN 303 645 IoT Security Baseline Governance

## Purpose

Govern the application of ETSI EN 303 645 (cyber security for consumer Internet of Things: baseline requirements) so that consumer IoT products the studio develops or procures meet a recognized security baseline: no universal default passwords, vulnerability disclosure, software updates, secure storage of credentials, and the other provision-level requirements, implemented and evidenced rather than asserted.

## Scope

Applies to every consumer IoT product the studio develops, brands, or procures — any product that connects to a network and is used in a consumer context. Covers the baseline provision set, data protection provisions, and conformance assessment approach. Does not cover industrial IoT (IEC 62443 governs that context) or general product safety.

## Workflow

1. Classify the product as consumer IoT where applicable and map each EN 303 645 provision to the product's design: universal default passwords (5.1), vulnerability disclosure (5.2), software updates (5.3), secure storage (5.4), secure communication (5.5), minimized exposed attack surfaces (5.6), protecting personal data (5.7), resilience of power and network (5.8-5.9), examining system telemetry (5.10), easy deletion of personal data (5.11), and installation/maintenance provisioning (5.12-5.13).
2. Implement the "no universal default password" provision with unique per-device credentials generated at manufacture or first use; shared default credentials are a product-blocking defect.
3. Publish a vulnerability disclosure policy with a named contact point and committed acknowledgment times, and operate the intake behind it (coordinated with ISO/IEC 29147 handling).
4. Define the software update policy explicitly: update period, end-of-support date published at or before purchase, and the update mechanism's own security; products with un-updatable software need a published support lifetime that consumers can see.
5. For each provision, record the implementation evidence — design document sections, test results, and policy texts — in the product's conformance file.
6. Assess conformance using the ETSI assessment methodology (TS 103 701) where third-party or self-declared assessment is needed, and record the outcome per provision.
7. Feed field findings from vulnerability disclosure and telemetry into the provision conformance review; a provision violated in practice re-opens the conformance file.

## Controls and evidence

- Provision-to-design mapping per product with implementation owner and evidence links.
- Vulnerability disclosure policy publication record and intake operation logs.
- Software update policy with published support period and update mechanism security review.
- Conformance file per product with assessment results per provision.
- Field finding records linked back to affected provisions.

## Validation

- Attempt first-use with a default credential in a test and confirm it fails where the provision requires uniqueness.
- Confirm the vulnerability disclosure contact resolves and acknowledgment times are being met.
- Confirm each product's support period is discoverable by a purchaser before purchase.

## Failure correction

- **Universal default credential discovered** → halt shipment, generate unique credentials for affected stock, publish remediation, and re-assess provision 5.1.
- **Disclosure intake unmonitored** → restore monitoring, review missed reports for unhandled vulnerabilities, and fix the operational ownership.
- **Support period unpublished** → publish immediately and backdate the disclosure to current owners.

## Limitations

- EN 303 645 is a baseline, not a comprehensive security standard; higher-risk products need proportionally stronger measures.
- Consumer IoT scope excludes explicitly enterprise/industrial equipment; classification decides which regime applies.
- Regulatory regimes (e.g., UK PSTI, EU Cyber Resilience Act) reference or build on this baseline with additional legal obligations; verify per market.

## Scope note

This article is part of the standards leaf. Cross-reference: `IEC_62443_2_1_VERSION_TRANSITION_GOVERNANCE.md`, `ISO_IEC_29147_2018_VULNERABILITY_DISCLOSURE_GOVERNANCE.md`, and `ENISA` IoT baseline guidance via the canonical sources.

## Canonical sources

- ETSI EN 303 645 — Cyber Security for Consumer Internet of Things: Baseline Requirements: https://www.etsi.org/deliver/etsi_en/303600_303699/303645/
- ETSI TS 103 701 — Cyber Security for Consumer IoT: Conformance Assessment: https://www.etsi.org/deliver/etsi_ts/103700_103799/103701/
- UK PSTI — Product Security and Telecommunications Infrastructure Act 2022 security requirements: https://www.gov.uk/government/collections/product-security-requirements
- ISO/IEC 27402 — IoT security and privacy — Device baseline requirements: https://www.iso.org/standard/80936.html
- ENISA — Baseline security recommendations for IoT: https://www.enisa.europa.eu/publications/baseline-security-recommendations-for-iot
