---
title: ISO/IEC 27017:2015 Cloud-Specific Information Security Controls Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 27017:2015 (first edition, 2015-12-15) — "Information technology — Security techniques — Code of practice for information security controls applicable to the provisioning and use of cloud services"; https://www.iso.org/standard/43757.html
---

# ISO/IEC 27017:2015 Cloud-Specific Information Security Controls Governance

## Scope

This card governs the application of ISO/IEC 27017:2015 controls to any cloud workload adopted or referenced by `orchords-docs`. It binds the KB expansion pipeline to specific cloud-provider responsibilities when a reference architecture cites AWS, Azure, GCP, or Alibaba Cloud.

## Why this card exists

ISO/IEC 27017 adds 37 cloud-specific controls on top of ISO/IEC 27002:2013, and re-frames 7 controls from a cloud-service-customer / cloud-service-provider perspective. Without a written mapping, the KB can recommend patterns that the provider does not actually own, producing audit gaps.

## Control families in scope

ISO/IEC 27017 adds controls in the following Annex A clauses:

- **A.5** — Information security policies (no additions; same as 27002)
- **A.6** — Organization of information security (no additions)
- **A.7** — Human resources security (no additions)
- **A.8** — Asset management (no additions)
- **A.9** — Access control (cloud additions)
- **A.10** — Cryptography (no additions)
- **A.11** — Physical and environmental security (cloud additions)
- **A.12** — Operations security (cloud additions)
- **A.13** — Communications security (no additions)
- **A.14** — System acquisition, development and maintenance (no additions)
- **A.15** — Supplier relationships (cloud additions)
- **A.16** — Incident management (cloud additions)
- **A.17** — Information security aspects of business continuity management (cloud additions)
- **A.18** — Compliance (cloud additions)

References: `https://www.iso.org/standard/43757.html` and ISO/IEC 27002:2013 (Annex A clause numbering).

## Cloud-specific controls — governance subset

| Control | Customer / Provider split | `orchords-docs` interpretation |
|---|---|---|
| CLD.1.1 — Capacity planning | Customer + Provider | Provider-owned infra; customer owns workload headroom; KB must call out autoscaler settings |
| CLD.1.2 — Monitoring of cloud services | Customer | KB cards cite CloudWatch / Azure Monitor / Cloud Monitoring as the only acceptable monitoring sink |
| CLD.1.5 — Virtual machine hardening | Customer | VM image references must trace to a hardening guide card |
| CLD.2.1 — Customer and provider responsibilities | Customer + Provider | RACI matrix required for every reference architecture card |
| CLD.3.1 — Use of virtual machines | Customer | Provider VM images must come from a documented catalogue |
| CLD.3.2 — Virtual machine images | Provider | Customer verifies image provenance; provider must publish attestation |
| CLD.4.1 — Segregation in shared virtual environments | Provider | KB does not assume hardware-level isolation; workload design must explicitly use VPC / subnet segregation |
| CLD.4.2 — Virtual machine environment protection | Provider + Customer | Identity-aware perimeter required at the workload boundary |
| CLD.4.3 — Virtual machine data confidentiality | Customer | CMK encryption must be customer-managed where the data class is restricted |
| CLD.4.5 — Virtual machine image sharing | Customer + Provider | Sharing image between accounts must be logged in PR with a justification |
| CLD.6.1 — Audit logging | Provider | Customer must export provider audit logs to its own sink within 24 hours |
| CLD.6.3 — Monitoring of cloud service agreements | Customer | Provider SOC 2 / ISO 27001 attestation must be on file |
| CLD.7.1 — Cloud service agreement contents | Provider + Customer | Provider must publish SLA; customer must align workload RTO/RPO to SLA |
| CLD.7.2 — Disclosure of customer information | Customer + Provider | Provider must publish subprocessors; customer must keep a subprocessor register |
| CLD.8.1 — Provisioning, modification, and withdrawal of cloud services | Customer | PR-level approval required to enroll a new cloud service |
| CLD.9.1 — Restriction of access to cloud services | Customer | Identity provider must be documented in the reference architecture card |
| CLD.9.2 — Identification of cloud service users | Customer | Every workload must use workload identity (no long-lived secrets) |
| CLD.9.3 — Removal of cloud service user access | Customer | Off-boarding SLA: ≤ 4 hours from HR ticket |
| CLD.9.4 — Audit of cloud service user access | Customer | Quarterly access review card under `docs/knowledge/playbooks/` |
| CLD.9.5 — Information shared between cloud service customer and provider | Customer + Provider | Every reference card that links a provider API must list data classification |

## Mapping to ISO/IEC 27002:2013

ISO/IEC 27017 explicitly inherits Annex A from 27002:2013 and adds cloud-specific overlays. The project maintains a mapping table from each 27017 control to its 27002 base, and from each mapping entry to a `docs/knowledge/` card that operationalizes it.

## Mandatory pre-flight (before adopting a new cloud provider)

1. Provider publishes an ISO/IEC 27017 attestation or an equivalent (CSA STAR, SOC 2 Type II).
2. Provider publishes a subprocessor list.
3. Provider publishes a customer-isolation architecture document.
4. Provider exposes audit-log APIs (CloudTrail, Azure Activity, Cloud Audit Logs) to the customer.
5. Provider SLA covers the workload RTO/RPO the reference architecture targets.
6. Workload identity (not long-lived keys) is configured end-to-end and tested in staging.

## Self-attestation cycle

Every 180 days a card author must:

1. Walk the cloud-provider reference architecture card and confirm every 27017 control that maps onto it.
2. Update the next-review date in this card's frontmatter.
3. Note any control gap in the change ticket; track remediation under a dated entry in the playbook `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## Sources

- ISO/IEC 27017:2015: `https://www.iso.org/standard/43757.html`
- ISO/IEC 27002:2013 (parent): `https://www.iso.org/standard/54533.html`
- ISO/IEC 27018:2019 (PII in public clouds): `https://www.iso.org/standard/76559.html`
- ISO/IEC 27036-4 (Supplier relationships): `https://www.iso.org/standard/81541.html`
- CSA STAR registry: `https://cloudsecurityalliance.org/star/registry/`
