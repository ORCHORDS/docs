# NIST SP 800-171 Controlled Unclassified Information (CUI) Safeguarding

## CUI system and contract boundary

NIST Special Publication 800-171, "Protecting Controlled Unclassified Information in Nonfederal Systems and Organizations," defines the safeguarding requirements that apply when a nonfederal entity processes, stores, or transmits Controlled Unclassified Information (CUI) on behalf of a federal agency. The publication was developed by the National Institute of Standards and Technology (NIST) in response to federal CUI regulations (32 CFR part 2002) and is referenced by acquisition regulations, including DFARS 252.204-7012 and DFARS 252.204-7019/7020 for the Department of Defense. This article covers the workflow for establishing the security requirement categories, mapping controls to systems that handle CUI, and capturing the evidence that supports an internal review. It does not cover NIST SP 800-53, which is the broader federal catalog, nor does it cover CMMC certification, which is a DoD-specific conformance program layered on top of 800-171.

## Requirement implementation sequence

1. **Determine that the system handles CUI.** The assessment begins by inventorying all federal contracts and subcontracts that flow CUI to the organization. If a contract clause requires safeguarding CUI, the CUI category is identified (e.g., export control, critical infrastructure, financial, tax) per 32 CFR part 2002 appendix.
2. **Define the system boundary.** The operational environment and the system boundary are described; the boundary includes every component that processes, stores, or transmits CUI. Boundary decisions follow the assessment boundary guidance in NIST SP 800-171A.
3. **Map the 14 requirement families to the system.** The 14 families (Access Control, Awareness and Training, Audit and Accountability, Configuration Management, Identification and Authentication, Incident Response, Maintenance, Media Protection, Personnel Security, Physical Protection, Risk Assessment, Security Assessment, System and Communications Protection, System and Information Integrity) are mapped to specific system components and policy references.
4. **Implement each requirement with concrete evidence.** Each requirement is documented with a policy statement, the responsible role, the implementation standard, and the evidence that supports the implementation. For example, multi-factor authentication (3.5.3) requires both a policy and a configuration screenshot showing the factor enforced at the boundary.
5. **Conduct a self-assessment.** The assessment is performed using the objectives in NIST SP 800-171A. The assessment is documented in a System Security Plan (SSP), a Plan of Action and Milestones (POA&M), and the resulting scoring in the DoD Supplier Performance Risk System (SPRS) when the contract references DFARS 252.204-7019/7020.
6. **Maintain on material change.** Any change to the system boundary, components, or configuration triggers a refresh of the SSP and the assessment; the POA&M is updated to reflect remediation progress.

## Asset, control, assessment, and POA&M data

The SSP carries the system name, the system description, the environment of operation, the authorization boundary diagram, the system categorization (FIPS 199 if applicable), the implementation for each requirement with a "met," "partially met," or "planned" status, the responsible role, the supporting policies, the implementation evidence reference, and a current assessment date. The POA&M carries the requirement identifier, the gap, the corrective action, the responsible owner, the scheduled completion date, and the status. The SPRS score is calculated using the DoD Assessment Methodology and is captured with a unique identifier and a date.

## Assessment and continuous-monitoring evidence

Validation evidence includes the configuration screenshots and policy references stored under each requirement. The assessment is validated through a second reviewer per requirement, a sample review of the evidence (configuration management records, audit logs, MFA enforcement), and a penetration test or vulnerability scan that supports the system and information integrity objectives. Validation of a fully met assessment is logged with the assessment date, the assessor identity, the reviewer's identity, and the SPRS submission identifier when applicable.

## Control-deficiency treatment

- **Boundary drift.** A system was added to the environment without being reflected in the SSP. The boundary document is updated, the new components are assessed against all 14 families, and the POA&M is regenerated; submissions to SPRS include the updated scope.
- **MFA not enforced.** The MFA control was documented as "met" but a configuration review found that remote access did not require the second factor. The system is remediated by enabling MFA at the boundary, the configuration screenshot is captured, and the SSP is updated.
- **Audit log gap.** The system was not capturing the audit records needed by the Audit and Accountability family. Logging is enabled, the log retention policy is confirmed, and the SSP is updated to reference the new log configuration.
- **Stale SPRS submission.** The SPRS submission expired (the scoring is a snapshot with a defined currency period). A new assessment is performed, the new score is submitted, and the prior submission is preserved for history.
- **Boundary encryption absent.** The system and communications protection requirements were not enforced because encryption was not configured on the database backup path. Encryption is enabled at rest and in transit, the configuration is captured, and the SSP is updated.

## Framework and contractual limits

Implementing a control set is not itself certification, authorization, or proof that every contract obligation is satisfied. Applicable revision, assessment method, agency clauses, CUI markings, and incident-reporting duties must be established from the controlling contract and current government publications.

## Canonical sources

- **Primary authority 1:** National Institute of Standards and Technology, *NIST SP 800-171 Rev. 2 — Protecting CUI in Nonfederal Systems and Organizations* — https://csrc.nist.gov/publications/detail/sp/800-171/rev-2/final
- **Primary authority 2:** National Archives and Records Administration, *Controlled Unclassified Information (CUI) Program* — https://www.archives.gov/cui
