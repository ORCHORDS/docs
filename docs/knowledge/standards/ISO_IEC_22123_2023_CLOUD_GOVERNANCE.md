---
title: ISO/IEC 22123:2023 Cloud Computing Reference Architecture Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 22123-1:2023 (Conceptual model); ISO/IEC 22123-2:2023 (Reference architecture); ISO/IEC 22123-3:2023 (Computing technologies); https://www.iso.org/standard/83828.html, https://www.iso.org/standard/83829.html, https://www.iso.org/standard/83830.html
---

# ISO/IEC 22123:2023 Cloud Computing Reference Architecture Governance

## Scope

This card governs how `orchords-docs` evaluates cloud computing reference architectures against ISO/IEC 22123:2023. It is the reference input for any KB card that cites cloud workloads, IaaS/PaaS/SaaS, or multi-cloud architectures.

## Why this card exists

ISO/IEC 22123 is the cloud computing reference architecture standard. It supersedes ISO/IEC 17789 and ISO/IEC 17788 in some jurisdictions and aligns with ISO/IEC 27017/27018/27033-3 cloud overlays. Without an explicit card, the KB cites cloud architectures that the cloud-security auditor cannot reconcile to the standard.

## Document set

- **ISO/IEC 22123-1:2023** — Conceptual model.
- **ISO/IEC 22123-2:2023** — Reference architecture.
- **ISO/IEC 22123-3:2023** — Computing technologies.

References: `https://www.iso.org/standard/83828.html`, `https://www.iso.org/standard/83829.html`, `https://www.iso.org/standard/83830.html`.

## Cloud computing characteristics

ISO/IEC 22123 defines five essential characteristics:

1. **Broad network access** — accessible via standard protocols.
2. **Rapid elasticity and scalability** — capacity can be elastically provisioned.
3. **Measured service** — usage is metered.
4. **Multi-tenancy** — multiple customers share resources.
5. **On-demand self-service** — provisioning without human interaction.

## Cloud service categories

| Category | Description | Examples |
|---|---|---|
| IaaS | infrastructure as a service | EC2, Azure VM, Compute Engine |
| PaaS | platform as a service | App Service, Cloud Run, App Engine |
| SaaS | software as a service | Office 365, Salesforce, GitHub |
| FaaS | function as a service | Lambda, Azure Functions, Cloud Functions |
| CaaS | container as a service | EKS, AKS, GKE |
| DBaaS | database as a service | RDS, Cosmos DB, Cloud SQL |

## Cloud deployment models

| Model | Description |
|---|---|
| Public | open to any customer |
| Private | single organization |
| Hybrid | combination of public and private |
| Community | shared by a community of organizations |
| Multi-cloud | multiple cloud providers |

## Cloud computing roles

| Role | Description |
|---|---|
| Cloud service customer | uses the cloud service |
| Cloud service provider | provides the cloud service |
| Cloud service partner | supports the provider (e.g., network carrier) |
| Cloud broker | aggregates / integrates cloud services |

## Reference architecture (Part 2)

The reference architecture defines:

- **Cloud service customer support** activities.
- **Cloud service provider support** activities.
- **Cloud service orchestration** — provisioning, configuration, monitoring.
- **Cloud service management** — SLAs, billing, security.
- **Cloud service security** — identity, encryption, key management.
- **Cloud service privacy** — data classification, consent.
- **Cloud service interoperability** — APIs, data formats.

## Cross-reference

| Domain | Card |
|---|---|
| Cloud security | `ISO_IEC_27017_2015_CLOUD_GOVERNANCE.md` |
| PII | `ISO_IEC_27018_2019_PII_GOVERNANCE.md` |
| PIMS | `ISO_IEC_27701_2019_PIMS_GOVERNANCE.md` |
| Network | `ISO_IEC_27033_2022_NETWORK_GOVERNANCE.md` |
| AI | `ISO_IEC_42001_2023_AIMS_GOVERNANCE.md` |

## Mandatory pre-flight (before adopting a new cloud service)

1. Service model (IaaS/PaaS/SaaS) is documented.
2. Deployment model is documented.
3. Roles and responsibilities are documented (per ISO/IEC 27017).
4. SLA is documented.
5. Compliance attestation is documented (27017, 27018).
6. Cross-region transfer mechanism is documented.
7. Encryption-at-rest policy is documented.

## Self-attestation cycle

Every 180 days:

1. Walk every cloud reference card.
2. Confirm conformance to ISO/IEC 22123.
3. Confirm conformance to ISO/IEC 27017/27018/27033-3.
4. Update the next-review date.

## Sources

- ISO/IEC 22123-1:2023: `https://www.iso.org/standard/83828.html`
- ISO/IEC 22123-2:2023: `https://www.iso.org/standard/83829.html`
- ISO/IEC 22123-3:2023: `https://www.iso.org/standard/83830.html`
- NIST SP 500-292 (NIST Cloud Computing Reference Architecture): `https://www.nist.gov/publications/nist-cloud-computing-reference-architecture`
