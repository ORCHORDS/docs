# NIST SP 800-146 (2012) Cloud Computing Synopsis and Recommendations Governance

## 1. Scope

This document records the governance controls applicable to the platform cloud programme in alignment with NIST SP 800-146 (2012), "Cloud Computing Synopsis and Recommendations." It defines the benefits, considerations, security recommendations, contractual artefacts, and compliance evidence required to operate, migrate to, and audit cloud systems. The card applies to engineering, infrastructure, security, and compliance teams responsible for deployment, oversight, and continuous assurance.

## 2. Normative references

The following documents are normative for this card:

- NIST SP 800-146, Cloud Computing Synopsis and Recommendations (2012).
- NIST SP 800-145, The NIST Definition of Cloud Computing.
- NIST SP 800-53 Rev. 5, Security and Privacy Controls.
- FedRAMP Authorization Act and OMB M-11-11 with successor memoranda.
- ISO/IEC 27001:2022, Information Security Management Systems.
- ISO/IEC 27017:2015, Code of Practice for Cloud Services.
- AICPA SSAE 18 SOC 2 Type II, Trust Services Criteria.

## 3. Terms and definitions

For the purposes of this card the following terms apply.

3.1 Cloud computing — A model for enabling ubiquitous, on-demand network access to a shared pool of configurable computing resources that can be rapidly provisioned and released with minimal management effort.

3.2 Provider — The party delivering the cloud service, including compute, storage, and network fabric.

3.3 Consumer — The organization acquiring and using the cloud service.

3.4 Governance — The framework of policies, roles, responsibilities, and decision rights directing the secure use of cloud resources.

3.5 Trust — The assured confidence, evidenced through audit and certification, that the provider will execute contractual controls.

## 4. Background

NIST SP 800-146 consolidates the federal understanding of cloud characteristics, delivery models (SaaS, PaaS, IaaS), and deployment models (private, community, public, hybrid). Its principal contribution is a structured set of recommendations spanning governance, architecture, operations, isolation, and data protection, linking to FedRAMP, ISO 27001, and SOC 2 as evidentiary instruments for regulated adoption.

## 5. Cloud computing benefits and considerations

5.1 Benefits. SP 800-146 §3 enumerates reduced capital expenditure and predictable operating expense through metered consumption, improved agility via on-demand provisioning, elasticity and scalability across workload peaks, and the freeing of staff from undifferentiated infrastructure maintenance.

5.2 Considerations. The same section enumerates considerations constraining those benefits: regulatory compliance obligations that travel with the workload, the shared control plane in which the consumer retains configuration duty while the provider retains physical duty, and vendor lock-in risk arising from proprietary interfaces, data formats, and egress economics. Each benefit is weighed against the corresponding consideration in the risk register at section 11.

## 6. Security recommendations: governance, compliance, trust

6.1 Governance. Establish a cloud governance board with documented charter, meeting cadence, and decision rights over migration, exit, and exception handling. Maintain an authoritative inventory of cloud assets, owners, and classifications, reviewed monthly.

6.2 Compliance. Map every regulatory obligation to a control implemented in provider or consumer environments; record residual obligations and evidence sources demonstrating satisfaction. Federal workloads shall pursue FedRAMP authorization at the appropriate baseline.

6.3 Trust. Trust shall be evidenced by independent third-party assessment. The provider must maintain a current FedRAMP Authorization to Operate, an active ISO 27001 certification, and a SOC 2 Type II report covering a minimum twelve-month observation window with no qualified opinions on Security and Availability.

## 7. Security recommendations: architecture and operations

7.1 Architecture. Architectures shall be documented against the shared responsibility model; consumer-side, provider-side, and joint duties shall be enumerated per service. Network topology shall use least-privilege segmentation, default-deny egress, and encrypted transport for inter-zone traffic.

7.2 Operations. Operational duties shall include identity and access management with role-based controls and periodic recertification, continuous logging to a tamper-resistant store, vulnerability scanning at a documented cadence, and patch management governed by a published service-level objective. Incident response procedures shall be exercised annually.

## 8. Security recommendations: software isolation, data protection, virtualization

8.1 Software isolation. Workloads shall execute within isolation primitives appropriate to the delivery model: container namespaces and seccomp profiles for PaaS, hypervisor-enforced separation for IaaS, and tenant-scoped application logic for SaaS.

8.2 Data protection. Data at rest shall be encrypted using FIPS 140-3 validated modules; data in transit shall be protected using current Transport Layer Security profiles; key management shall support customer-managed keys with documented rotation. Data classification shall govern residency and retention.

8.3 Virtualization. Virtualization layers shall be hardened against escape and side-channel attacks; hypervisors shall be patched within documented service-level objectives, and live migration shall be subject to integrity attestation.

## 9. Recommended contractual artefacts (SLA, NDA, EULA)

9.1 Service Level Agreement. The SLA shall commit to a defined availability objective, response and resolution targets by severity, scheduled maintenance windows, service credits, and termination rights for sustained non-conformance. Reporting shall be auditable and machine-readable.

9.2 Non-Disclosure Agreement. The NDA shall protect confidential information exchanged during onboarding, audits, and incident response; it shall cover trade secrets, security architecture, vulnerability data, and personal information, with a survival clause consistent with the retention schedule.

9.3 End User Licence Agreement. The EULA shall define acceptable use, prohibitions on reverse engineering and unauthorized resale, allocation of liability, indemnity scope, governing law, and dispute resolution mechanics.

## 10. Compliance evidence (FedRAMP, ISO 27001, SOC 2)

10.1 FedRAMP. The provider shall produce a current Authorization to Operate letter, the corresponding Security Assessment Report, and the Plan of Action and Milestones. Material changes shall trigger a continuous monitoring submission.

10.2 ISO 27001. The provider shall produce a valid ISO 27001 certificate issued by an accredited body, with the Statement of Applicability and the most recent surveillance or recertification audit report.

10.3 SOC 2. The provider shall produce an annual SOC 2 Type II report covering Security, Availability, and Confidentiality, with the carve-out method disclosed; bridge letters shall cover intervening periods.

## 11. Risk register

| ID | Risk | Likelihood | Impact | Treatment |
|----|------|------------|--------|-----------|
| R1 | Regulatory non-compliance across jurisdictions | Medium | High | Compliance mapping; cross-region evidence retention |
| R2 | Loss of control plane visibility | Medium | High | Continuous logging; provider API telemetry |
| R3 | Vendor lock-in | Medium | Medium | Multi-cloud abstraction; portable data formats |
| R4 | Data residency breach | Low | High | Region pinning; consumer-managed encryption keys |
| R5 | Hypervisor escape | Low | Critical | Hardened images; timely patching; attestation |
| R6 | Egress cost escalation | Medium | Medium | Budget alarms; tiered storage strategy |
| R7 | Certification lapse | Low | High | Contractual re-certification covenants; calendar |

## 12. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.