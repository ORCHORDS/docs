# NIST SP 800-144 (2011) Guidelines on Security and Privacy in Public Cloud Computing Governance

## 1. Scope

This card codifies governance expectations derived from NIST Special Publication 800-144, "Guidelines on Security and Privacy in Public Cloud Computing," as applied within regulated programme work. It applies to information systems that consume public cloud services across Infrastructure as a Service (IaaS), Platform as a Service (PaaS), and Software as a Service (SaaS) delivery models. The card addresses governance, risk, and compliance obligations of the cloud customer, the cloud provider, and any integrator acting between them. It does not supersede the underlying publication; where conflict arises, the publication governs.

## 2. Normative references

The following documents are indispensable to the application of this card. For dated references, only the cited edition applies.

- NIST SP 800-144, Guidelines on Security and Privacy in Public Cloud Computing (December 2011).
- NIST SP 800-145, The NIST Definition of Cloud Computing.
- NIST SP 800-146, Cloud Computing Synopsis and Recommendations.
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations.
- ISO/IEC 27001:2022, Information security, cybersecurity and privacy protection — Information security management systems — Requirements.
- ISO/IEC 27017:2015, Code of practice for information security controls applicable to the provision and use of cloud services.
- ISO/IEC 27018:2019, Code of practice for protection of personally identifiable information in public clouds acting as PII processor.
- AICPA TSP Section 100 (2017, with 2022 revisions), Trust Services Criteria for Security, Availability, Processing Integrity, Confidentiality, and Privacy.
- FedRAMP Authorization Act (44 U.S.C. § 3609 et seq.) and the FedRAMP Security Controls Baseline.
- BSI Cloud Computing Compliance Criteria Catalogue (C5:2020).
- Regulation (EU) 2016/679 (General Data Protection Regulation).

## 3. Terms and definitions

For the purposes of this card, the following definitions apply.

- **IaaS** — Infrastructure as a Service: the capability provided to the consumer to provision processing, storage, networks, and other fundamental computing resources where the consumer can deploy and run arbitrary software.
- **PaaS** — Platform as a Service: the capability provided to the consumer to deploy onto the cloud infrastructure consumer-created or acquired applications created using programming languages, libraries, services, and tools supported by the provider.
- **SaaS** — Software as a Service: the capability provided to the consumer to use the provider's applications running on a cloud infrastructure; the applications are accessible from various client devices through a thin client interface such as a web browser.
- **Cloud customer** — the organization that establishes a contractual relationship with a cloud provider for the use of cloud services.
- **Cloud provider** — the organization that provides cloud services to a cloud customer under a service-level agreement.
- **Shared responsibility** — the division of security and privacy obligations between provider and customer as a function of the service model.

## 4. Background

Public cloud computing introduces a fundamental shift in how computing resources are provisioned, consumed, and governed. NIST SP 800-144 characterizes the trade-off between the operational and economic benefits of public cloud services and the security and privacy concerns inherent in transferring data and processing outside the customer's traditional security perimeter. The publication identifies governance as the overarching control family that determines whether lower-layer technical, operational, and contractual controls are likely to remain effective throughout the service relationship.

## 5. Cloud service models and deployment models

Cloud services are categorized by NIST SP 800-145 into three service models and four deployment models. The service models are IaaS, PaaS, and SaaS, as defined in §3. The deployment models comprise public cloud, private cloud, hybrid cloud, and community cloud. A public cloud is provisioned for open use by the general public. A private cloud is provisioned for exclusive use by a single organization. A hybrid cloud composes two or more distinct cloud infrastructures bound by standardized or proprietary technology that enables data and application portability. A community cloud is provisioned for exclusive use by a specific community of consumers from organizations that have shared concerns. Cross-reference: see [NIST SP 800-145 Cloud Governance](../standards/NIST_SP_800_145_CLOUD_GOVERNANCE.md).

## 6. Shared responsibility matrix

Security and privacy obligations are partitioned between provider and customer as a function of the service model. Under IaaS, the provider is responsible for the physical facility, host operating system, virtualization layer, network, and storage substrate; the customer retains responsibility for guest operating systems, middleware, application code, data, identity, and access control. Under PaaS, the provider additionally assumes responsibility for the runtime, middleware, and development tooling; the customer retains responsibility for application code, configuration, data, and identity. Under SaaS, the provider assumes responsibility for the application and most configuration; the customer retains responsibility for user access, data classification, data lifecycle, and client-side endpoint integrity. Cross-reference: see [FedRAMP Rev. 5 MOD Governance](../standards/FEDRAMP_REV_5_MOD_GOVERNANCE.md) and [NIST SP 800-53 Rev. 5 Security Governance](../standards/NIST_SP_800_53_R5_SECURITY_GOVERNANCE.md).

## 7. Security and privacy risks in public cloud

The following risks are enumerated for governance tracking. Each risk shall be scored, assigned an owner, and tracked in the risk register per §11.

1. **Data loss** — accidental deletion, malicious overwrite, or provider outage resulting in unrecoverable customer data.
2. **Multi-tenancy exposure** — logical co-tenantion failures that allow one tenant to observe, affect, or extract another tenant's data or workloads.
3. **Governance loss** — inability of the customer to enforce internal policies, audit trails, or contractual obligations once control planes are delegated to the provider.
4. **Compliance uncertainty** — ambiguity regarding which legal regimes, certifications, or sectoral obligations apply to data once it crosses jurisdictional or provider boundaries.
5. **Vendor lock-in** — dependence on proprietary interfaces, data formats, or pricing structures that materially raise the cost of exit and reduce negotiating leverage.

## 8. Controls and mitigations

Controls are selected from NIST SP 800-53 Rev. 5 and mapped to the risks in §7. Key control families include AC (Access Control), AU (Audit and Accountability), CM (Configuration Management), IA (Identification and Authentication), IR (Incident Response), MP (Media Protection), SC (System and Communications Protection), SI (System and Information Integrity), and SR (Supply Chain Risk Management). Mitigation strategies include encryption of data in transit and at rest under customer-held keys, customer-managed identity and access, contractual audit and logging rights, separation of duties between customer and provider administrators, and documented exit and portability plans.

## 9. Compliance evidence

Acceptable evidence packages for public cloud deployments shall include the following. For U.S. federal workloads, FedRAMP authorization at the appropriate baseline (Low, Moderate, or High) is required. For commercial and international deployments, ISO/IEC 27001 certification with a supporting Statement of Applicability is required. Independent service auditor reports shall be obtained as AICPA SOC 2 Type II reports covering Security, Availability, and Confidentiality Trust Services Criteria. For European and German federal workloads, BSI C5:2020 attestation at Type 1 or Type 2 shall be obtained. Cross-reference: see [FedRAMP Rev. 5 MOD Governance](../standards/FEDRAMP_REV_5_MOD_GOVERNANCE.md), [NIST SP 800-53A Rev. 5 Assessment Governance](../standards/NIST_SP_800_53A_REV5_ASSESSMENT_GOVERNANCE.md), and [NIST SP 800-53 Rev. 5 Control Catalog Governance](../standards/NIST_SP_800_53_R5_2_CONTROL_CATALOG_GOVERNANCE.md).

## 10. SOAR (Security Orchestration Automation and Response) integration for cloud-native incident response

Cloud-native incident response shall integrate with a Security Orchestration, Automation, and Response (SOAR) platform. The SOAR layer shall ingest native telemetry from the cloud provider (CloudTrail, Azure Activity, GCP Cloud Audit Logs), the customer identity provider, endpoint detection agents, and the security information and event management (SIEM) platform. Playbooks shall cover credential compromise, data exfiltration, configuration drift against approved baselines, and provider outage. Automated actions shall be limited to reversible containment actions; destructive actions require human approval. SOAR run logs form part of the audit evidence required under §9.

## 11. Risk register

| Risk ID | Risk | Likelihood | Impact | Inherent score | Owner | Review date |
|---------|------|-----------|--------|----------------|-------|-------------|
| R-CLD-01 | Data loss | Medium | High | High | Data Protection Officer | 2027-03-07 |
| R-CLD-02 | Multi-tenancy exposure | Low | High | Medium | Cloud Security Architect | 2027-03-07 |
| R-CLD-03 | Governance loss | Medium | High | High | GRC Lead | 2027-03-07 |
| R-CLD-04 | Compliance uncertainty | Medium | Medium | Medium | Compliance Officer | 2027-03-07 |
| R-CLD-05 | Vendor lock-in | High | Medium | High | Procurement Lead | 2027-03-07 |

## 12. Review cadence

This card is reviewed at least every 180 days, or upon any of the following triggers: material change to a referenced standard, material change to a contracted service model, material change in threat landscape, or post-incident lessons learned. The review confirms continued alignment with NIST SP 800-144 and the normative references in §2.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
