---
title: ISO/IEC 27018:2019 PII Protection in Public Cloud Services Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 27018:2019 (second edition, 2019-01-08) — "Information technology — Security techniques — Code of practice for protection of personally identifiable information in public clouds acting as PII processor"; https://www.iso.org/standard/76559.html
---

# ISO/IEC 27018:2019 PII Protection in Public Cloud Services Governance

## Scope

This card governs how `orchords-docs` evaluates public-cloud PII handling against ISO/IEC 27018:2019. The card is the reference input for any reference architecture that designates a public cloud (AWS, Azure, GCP, Alibaba) as a **PII processor**.

## Why this card exists

ISO/IEC 27018 is the public-cloud-specific overlay of ISO/IEC 27002, with explicit obligations on the public-cloud PII processor (the cloud provider) and obligations on the PII controller (the customer). Without an explicit card, the KB can recommend a public-cloud service without confirming which 27018 controls the provider has publicly committed to.

## Document structure

ISO/IEC 27018:2019 (second edition) restates ISO/IEC 27002 controls with public-cloud-specific guidance and adds Annex A controls that apply only when the organization acts as a PII processor in a public cloud. The document does **not** include ISO/IEC 27001 conformance requirements; it is a code of practice.

References: `https://www.iso.org/standard/76559.html`.

## Annex A — Public-cloud PII processor controls (subset)

| Control | Title | Project obligation |
|---|---|---|
| A.5.1 | Customer agreement obligation | every cloud-provider reference card must cite the DPA terms |
| A.5.2 | Customer agreement purpose | provider must process only for the customer-stated purpose |
| A.5.3 | Customer agreement transparency | provider must publish the categories of PII processed |
| A.6.1 | Use, retention, and disclosure of PII | retention and disclosure must be auditable |
| A.7.1 | Return, transfer, or disposal of PII | end-of-life must return to customer or attest destruction |
| A.7.2 | Cooperation with customer | provider must support customer audit requests |
| A.7.3 | Disclosure to third parties | disclosure only to published subprocessor list |
| A.8.1 | Information for the customer | provider must publish operational changes |
| A.8.2 | Disclosure of breaches | provider breach feed to customer ≤ 24 hours |
| A.8.3 | Notification of breaches | same as A.8.2 |
| A.9.1 | Subcontracted PII processing | provider must obtain customer authorization for subprocessors |
| A.9.2 | Subprocessor list | published subprocessor list |
| A.9.3 | Subprocessor changes | customer notification on change |
| A.10.1 | Confidentiality undertaking | provider employees must be under confidentiality |
| A.10.2 | Return, transfer, or disposal of PII at end of service | same as A.7.1 |
| A.11.1 | Information security incident management | provider must publish incident management procedures |

References: ISO/IEC 27018:2019 Annex A.

## Mapping to ISO/IEC 27017 and 27701

The three ISO standards overlap:

- **ISO/IEC 27017** — cloud-specific security controls (applies to all cloud workloads, not just PII).
- **ISO/IEC 27018** — public-cloud PII processor obligations.
- **ISO/IEC 27701** — privacy information management system (PIMS), controller + processor.

The KB uses 27017 for general cloud security, 27018 for public-cloud PII processor due diligence, and 27701 for the broader PIMS that ties controllers and processors together. Reference cards that touch public-cloud PII must cite all three.

## Provider attestation evidence

Public-cloud providers that publish 27018 attestation include (incomplete list):

| Provider | 27018 attestation | Status |
|---|---|---|
| Microsoft Azure | yes (independent audit) | current |
| Amazon Web Services | yes (independent audit) | current |
| Google Cloud Platform | yes (independent audit) | current |
| Oracle Cloud Infrastructure | yes | current |
| Alibaba Cloud | yes (regional scope) | current |
| IBM Cloud | yes | current |
| DigitalOcean | no | not pursued |
| Linode | no | not pursued |

A provider without a current 27018 attestation cannot be cited in a reference card that handles PII.

## Mandatory pre-flight (before adopting a public cloud provider for PII)

1. Provider publishes a current ISO/IEC 27018 attestation (independent audit).
2. Provider publishes a subprocessor list with version history.
3. Provider DPA references the ISO/IEC 27018 commitments.
4. Provider SLA covers the workload RTO/RPO.
5. Provider exposes a breach-notification feed within 24 hours.
6. Customer (the project) has an ISO/IEC 27701 PIMS in place that covers the workload.

## Self-attestation cycle

Every 180 days, the project must:

1. Re-confirm the provider attestation is current.
2. Walk every public-cloud reference card and confirm it cites 27018.
3. Confirm the subprocessor list is current.
4. Update the next-review date.

## Sources

- ISO/IEC 27018:2019: `https://www.iso.org/standard/76559.html`
- ISO/IEC 27017:2015: `https://www.iso.org/standard/43757.html`
- ISO/IEC 27701:2019: `https://www.iso.org/standard/71670.html`
- ISO/IEC 27018 attestation registers (provider-specific): see provider trust center
- EuroCloud Europe — ISO/IEC 27018 audit guide
