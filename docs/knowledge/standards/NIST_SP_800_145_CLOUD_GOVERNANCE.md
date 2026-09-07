# NIST SP 800-145 (2011) The NIST Definition of Cloud Computing Governance

## 1. Scope

This card establishes a governance overlay for the consumption, provision, and audit of cloud computing services. It adopts the definition of cloud computing published by the National Institute of Standards and Technology in Special Publication 800-145 (September 2011) and binds that definition to internal controls, evidence requirements, and review cadence. The scope covers all cloud service models (SaaS, PaaS, IaaS) and all cloud deployment models (private, community, public, hybrid), regardless of hosting provider or jurisdiction.

## 2. Normative references

The following documents are indispensable for the application of this card:

- NIST Special Publication 800-145, The NIST Definition of Cloud Computing, September 2011.
- NIST Special Publication 800-53, Security and Privacy Controls for Information Systems and Organizations.
- NIST Special Publication 800-37, Risk Management Framework for Information Systems and Organizations.
- FedRAMP Authorization Act (44 U.S.C. § 3601 et seq.) and the FedRAMP Authorization Baseline.
- ISO/IEC 17788, Information technology — Cloud computing — Overview and vocabulary.
- ISO/IEC 27001, Information security management systems — Requirements.

## 3. Terms and definitions

For the purposes of this card, the following terms and definitions apply.

**Cloud computing**: a model for enabling ubiquitous, convenient, on-demand network access to a shared pool of configurable computing resources (e.g., networks, servers, storage, applications, and services) that can be rapidly provisioned and released with minimal management effort or service provider interaction.

**On-demand self-service**: a cloud capability whereby a consumer can unilaterally provision computing capabilities, such as server time and network storage, automatically as needed without requiring human interaction with each service provider.

**Broad network access**: a cloud capability whereby capabilities are available over the network and accessed through standard mechanisms used by heterogeneous client platforms (e.g., mobile phones, tablets, laptops, and workstations).

**Resource pooling**: a cloud capability whereby the provider's computing resources are pooled to serve multiple consumers using a multi-tenant model, with physical and virtual resources dynamically reassigned according to consumer demand.

**Rapid elasticity**: a cloud capability whereby capabilities can be elastically provisioned and released, in some cases automatically, to scale rapidly outward and inward commensurate with demand.

**Measured service**: a cloud capability whereby cloud systems automatically control and optimize resource use by leveraging metering at some level of abstraction appropriate to the type of service (e.g., storage, processing, bandwidth, and active user accounts). Resource usage can be monitored, controlled, and reported, providing transparency for both the provider and consumer of the utilized service.

## 4. Background

NIST SP 800-145 was issued to provide a concise, formal definition of cloud computing that distinguishes it from other distributed computing paradigms. The publication identifies three service models, four deployment models, and five essential characteristics that together constitute a cloud computing system. Because the definition is technology-neutral and provider-neutral, it has been adopted as a reference vocabulary by federal agencies, auditors, and commercial customers. This card re-states the NIST vocabulary and binds it to the organization's evidence and review obligations.

## 5. Essential characteristics of cloud computing

A system is a cloud computing system only when it exhibits all five of the following essential characteristics, as defined by NIST SP 800-145:

1. On-demand self-service.
2. Broad network access.
3. Resource pooling.
4. Rapid elasticity.
5. Measured service.

If any of the five characteristics is absent or only partially implemented, the offering is not classified as cloud computing for the purposes of this card and shall be assessed under the corresponding non-cloud governance baseline.

## 6. Cloud service models

NIST SP 800-145 defines three service models. The consumer-provider division of responsibility differs in each.

**Software as a Service (SaaS)**: the consumer uses the provider's applications running on a cloud infrastructure. The consumer does not manage or control the underlying cloud infrastructure, with the possible exception of limited user-specific application configuration settings. Examples: hosted electronic mail, customer relationship management platforms, and office productivity suites delivered through a browser.

**Platform as a Service (PaaS)**: the consumer deploys onto the cloud infrastructure provider-created applications, or applications acquired from third parties, using programming languages, libraries, services, and tools supported by the provider. The consumer does not manage or control the underlying cloud infrastructure but has control over the deployed applications and possibly over application hosting environment configurations. Examples: managed application runtimes, database-as-a-service platforms, and integration brokers.

**Infrastructure as a Service (IaaS)**: the consumer is provided with processing, storage, networks, and other fundamental computing resources and is able to deploy and run arbitrary software, which can include operating systems and applications. The consumer does not manage or control the underlying cloud infrastructure but has control over operating systems, storage, and deployed applications, and possibly limited control over select networking components. Examples: virtualized servers, block storage volumes, and virtual private networks delivered as services.

## 7. Cloud deployment models

NIST SP 800-145 defines four deployment models.

**Private cloud**: the cloud infrastructure is provisioned for exclusive use by a single organization comprising multiple business units. It may be owned, managed, and operated by the organization, a third party, or some combination, and may exist on or off premises.

**Community cloud**: the cloud infrastructure is provisioned for exclusive use by a specific community of consumers from organizations that have shared concerns (e.g., mission, security requirements, policy, compliance considerations). It may be owned, managed, and operated by one or more organizations in the community, a third party, or some combination, and may exist on or off premises.

**Public cloud**: the cloud infrastructure is provisioned for open use by the general public. It may be owned, managed, and operated by a commercial, academic, or government organization, or some combination, and exists on the premises of the cloud provider.

**Hybrid cloud**: the cloud infrastructure is a composition of two or more distinct cloud infrastructures (private, community, or public) that remain unique entities but are bound together by standardized or proprietary technology that enables data and application portability.

## 8. Reference architecture and shared responsibility

Cloud architectures are decomposed into the application, platform, infrastructure, and physical layers. Responsibility for each layer is allocated between consumer and provider according to the service model. In SaaS, the provider retains responsibility for the platform, infrastructure, and physical layers; in PaaS, the provider retains responsibility for the infrastructure and physical layers while the consumer manages the application and configuration; in IaaS, the consumer assumes responsibility for the operating system, middleware, runtime, and application layers, while the provider retains responsibility for the physical infrastructure and virtualization. The allocation is recorded in the system security plan and reviewed at every change of service model. See `architecture/shared_responsibility_matrix.md:1` for the canonical allocation matrix.

## 9. Compliance evidence

Evidence of compliance with this card is produced through the Federal Risk and Authorization Management Program (FedRAMP) for federal cloud services, and through the NIST Risk Management Framework (RMF) for all systems. FedRAMP authorization artifacts (Security Assessment Report, System Security Plan, Plan of Action and Milestones, and Continuous Monitoring evidence) and RMF artifacts (categorization, control selection, implementation, assessment, authorization, and monitoring steps) are maintained in the compliance repository and referenced from each cloud system record. See `compliance_repository/fedramp_index.md:1` for the canonical FedRAMP artifact index and `compliance_repository/rmf_index.md:1` for the RMF step mapping.

## 10. Risk register

Risks associated with cloud computing adoption shall be recorded in the organizational risk register, including: provider concentration, data sovereignty, vendor lock-in, account credential compromise, misconfigured access controls, insufficient logging, insecure APIs, denial of service, shared-technology vulnerabilities, and non-compliance with applicable legal and regulatory regimes. Each risk shall be assigned an owner, a likelihood, an impact, a residual risk rating, and a treatment plan. See `risk_register/CLOUD.md:1` for the canonical cloud risk register.

## 11. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
