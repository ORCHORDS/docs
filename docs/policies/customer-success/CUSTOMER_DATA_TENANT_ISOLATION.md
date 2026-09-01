---
title: "Customer Data Tenant Isolation"
owner: "Customer Success Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Customer Data Tenant Isolation

## Purpose

Establish an accountable, evidence-based approach to tenant isolation for the systems that store, process, or expose customer-success data. The objective is to ensure that one customer's data is never observable, retrievable, or actionable by another customer — and that internal users who handle customer-success data operate within the boundaries their role and purpose require.

## Scope

This policy applies to any system, database, file share, analytics store, automation pipeline, support tool, or communication surface that holds customer-success data and that is shared between customers, between customer-success personnel, or between the customer-success function and adjacent functions. It does not replace the broader information-security management system, which governs all data classes; it focuses on the boundary conditions specific to multi-tenant customer-success contexts.

## Requirements

- Every system that holds customer-success data MUST identify its tenancy model: per-customer isolation, shared-schema with logical separation, or shared-process with logical separation. The model MUST be documented and approved.
- A system that stores per-customer data MUST enforce logical separation at the access-control layer. The control MUST apply at the application, the data layer, and any reporting or analytics extract that touches the data.
- Logical separation MUST be enforced by a single, named control point (such as a row-level security policy, a query interceptor, or a tenant-scoped service principal). Ad-hoc filtering in application code is NOT a substitute for the control point.
- Encryption MUST be applied to customer-success data at rest and in transit. Keys MUST be managed under the documented key-management policy, with separation between key custodians and data custodians.
- Customer-success personnel MUST operate under a documented role-based access model. Roles MUST grant the minimum access necessary for the purpose; access beyond the minimum MUST be justified, time-bounded, and approved.
- Access to customer-success data MUST be logged. Logs MUST record the actor, the purpose stated at the time of access, the data classes touched, and the timestamp. Logs MUST be retained for the documented period and reviewed for anomalous access.
- Privileged operations (export, bulk read, cross-tenant query, configuration change) MUST require an additional approval. The approver MUST be independent of the operator.
- Customer-success data MUST be classified by sensitivity. Access to higher-sensitivity data MUST be restricted to a smaller, named population, with additional approval and logging applied.
- Test, training, and development environments MUST NOT contain live customer data. Where live data is required for a specific, justified purpose, it MUST be irreversibly transformed (tokenised, masked, or synthesised) before it leaves the production boundary, and the transformation MUST be verified.
- Customer-success analytics MUST aggregate before they cross a tenant boundary. Reports that cross a boundary MUST NOT contain identifying detail for an individual customer unless the report's purpose and the recipient's role justify the exposure, and the recipient is bound by an equivalent isolation policy.
- Customer-success data MUST be retained only for the documented period. Retention enforcement MUST be automatic; manual deletion is permitted only with documented approval and audit trail.
- Where a regulatory or contractual obligation requires additional isolation (for example, jurisdiction-specific residency, sector-specific segregation, or air-gapped deployment), the additional isolation MUST be implemented as an explicit configuration of the system and verified before customer data is loaded.
- Tenant isolation MUST be tested before each material release and at least once per review cycle. Tests MUST include both a positive case (legitimate access succeeds) and a negative case (cross-tenant access is denied). Test results MUST be retained.
- Customer-success data MUST NOT be co-mingled with employee personal data, marketing lead data, or any other data class whose access pattern is different from the customer-success purpose.
- Cross-tenant data exposure incidents MUST be reported through the incident response process. The report MUST identify the affected tenants, the data classes exposed, the mitigation, and the corrective action.

## Controls

- A tenant-isolation control point is implemented at the access-control layer of every multi-tenant system. The control point is version-controlled and reviewed at each release.
- A row-level or query-level test corpus exercises cross-tenant access attempts; failures block promotion.
- An access-recertification cycle reviews every privileged role at least once per review cycle and revokes unneeded entitlements.
- A key-rotation cadence is enforced; rotation is logged and exceptions are escalated.
- A break-glass procedure provides emergency access under additional approval, time-bound, and logged.
- A pseudonymisation and synthetic-data pipeline provides safe test data for non-production use.

## Canonical sources

- ISO/IEC 27001:2022, Information security management — Requirements: https://www.iso.org/standard/27001
- ISO/IEC 27002:2022, Information security, cybersecurity and privacy protection — Information security controls: https://www.iso.org/standard/75652.html
- NIST SP 800-53 Rev. 5, Security and Privacy Controls for Information Systems and Organizations: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-204D, Implementation of DevSecOps for a Microservices-based Application with Service Mesh (public draft references for multi-tenant isolation): https://csrc.nist.gov/pubs/sp/800/204/d/final
- Cloud Security Alliance, Security Guidance for Critical Areas of Focus in Cloud Computing: https://cloudsecurityalliance.org/research/guidance/
- ISO/IEC 27018:2019, Code of practice for protection of personally identifiable information in public clouds acting as PII processors: https://www.iso.org/standard/76559.html
- ISO/IEC 27701:2019, Extension to ISO/IEC 27001 and ISO/IEC 27002 for privacy information management: https://www.iso.org/standard/71670.html
- OECD, Guidelines on the Protection of Privacy and Transborder Flows of Personal Data: https://www.oecd.org/digital/privacy-guidelines/