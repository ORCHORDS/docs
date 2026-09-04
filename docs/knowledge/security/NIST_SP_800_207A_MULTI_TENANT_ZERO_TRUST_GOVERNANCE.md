# NIST SP 800-207A — A Zero Trust Architecture Model for Access Control in Cloud-Native Applications in Multi-Cloud Environments

## Purpose

Establish governance on the design and operation of Zero Trust Architecture (ZTA) access control for cloud-native, multi-tenant applications that span multiple cloud service providers (CSPs). This article's scope is limited to multi-cloud, multi-tenant extensions of the Zero Trust model defined in NIST SP 800-207; it does not restate the parent document.

## Current status

- Published as Final on 2023-09-13 by the National Institute of Standards and Technology (NIST), Information Technology Laboratory, Computer Security Division.
- Publication Part of NIST SP 800-207 (Zero Trust Architecture).
- Authors: Ramaswamy Chandramouli and Zack Butcher.
- DOI: 10.6028/NIST.SP.800-207A.
- Companion-only: there is no predecessor revision. SP 800-207A is positioned as the multi-cloud/multi-tenant companion and explicitly defers all general ZTA concepts to SP 800-207.
- Free public download available from the NIST Computer Security Resource Center (CSRC).
- Status as of 2026-09-04: still authoritative current version; no superseding revision located.

## Sources

- Primary: NIST Special Publication 800-207A, https://doi.org/10.6028/NIST.SP.800-207A (publication landing page); canonical PDF hosted on csrc.nist.gov.
- Companion referenced: NIST SP 800-207 (Zero Trust Architecture), Black, P., et al., 2020-08, https://csrc.nist.gov/publications/detail/sp/800-207/final
- Authoritative context: NIST SP 800-204 (Security Strategies for Microservices-based Application Systems) and SP 800-210 (General Access Control Guidance for Cloud Systems), both cited within 207A.

## Scope note

SP 800-207A addresses a category of access control problems distinct from the single-organization, single-cloud ZTA model in SP 800-207. It applies where the application is partitioned into microservice tenants and is deployed across more than one CSP or more than one cloud account/project. The core governance-oriented concepts in the document, which should be reflected in any governed adoption, are:

1. Tenant as the access control subject. SP 800-207A treats "tenant" as the unit of trust inside a cloud-native application, not as an organizational customer. Each tenant has its own identity provider (IdP), its own policy administration point (PAP), and its own subset of microservices.
2. Five logical components per tenant. The document defines Tenant Identity Provider, Tenant Policy Engine (PEP/PDP), Microservice Instance, Tenant Data Store, and Tenant Trust Anchor. Governance artifacts (policies, audit logs, signed attestations) are produced and consumed per tenant.
3. Three general models. SP 800-207A organizes multi-cloud deployment into (a) single-cloud, single-tenant reference; (b) multi-cloud, single-tenant federation; (c) multi-cloud, multi-tenant brokered model. Governance controls and audit scope differ by model; the brokered model requires explicit trust handling across CSPs.
4. Multi-cloud policy portability. The document recommends that tenant-level access policies be expressed in a portable representation rather than embedded in CSP-native constructs so that the same policy can be evaluated consistently across providers.
5. Tailored trust anchors. SP 800-207A calls for trust anchors (root CAs, attestation roots, identity roots) to be selected per tenant and documented in the governance record; reusing an enterprise anchor across all tenants without per-tenant attestation is flagged as an anti-pattern.

This article does not cover SP 800-207 (covered separately under NIST_SP_800_207_ZERO_TRUST_ARCHITECTURE_GOVERNANCE.md), nor does it address federal identity requirements beyond what 207A itself incorporates.
