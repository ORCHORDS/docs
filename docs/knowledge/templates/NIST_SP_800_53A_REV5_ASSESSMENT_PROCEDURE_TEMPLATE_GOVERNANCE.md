# NIST SP 800-53A Rev 5 Assessment Procedure Template Governance

## Purpose
Establish the governance pattern for templating security and privacy control assessment procedures per NIST SP 800-53A Rev 5 (Assessing Security and Privacy Controls in Information Systems and Organizations).

## Scope
Applies to every assessment of a control baseline carried out under the studio's authorization program, regardless of whether the assessment is for initial authorization, continuous monitoring, or annual assessment.

## Workflow
1. Use a templated assessment procedure with mandatory elements per NIST SP 800-53A Rev 5: assessment objective, determination statements (one or more), assessment methods (examine, interview, test), and assessment objects.
3. For each assessment object, identify the artifact set (e.g., policy document, configuration file, log file) required to satisfy the determination statements.
5. Record the assessment result per determination statement: satisfied, other-than-satisfied, or not applicable. Use the studio's standardized severity scale for other-than-satisfied findings (low, moderate, high).
7. Capture assessor identity, assessment window, and authorization boundary in the procedure metadata.
9. Track the assessment record alongside the corresponding control entry in the System Security Plan (SSP) so traceability is preserved across authorization artefacts.

## Controls and evidence
- Assessment procedure repository with template identifier, control identifier, owner, and last-review date.
- Completed assessment records with determination-statement-level results, assessor identity, and assessment window.
- Mapping from each assessment finding to a Plan of Action and Milestones (POA&M) entry, where applicable.
- Annual review of the assessment procedure template against the latest NIST SP 800-53A publication.

## Validation
- Re-validate a sample of 10 assessment records against the corresponding template and confirm that every determination statement is addressed.
- Verify that every other-than-satisfied finding has an associated POA&M entry with target completion date.
- Confirm the assessment window covers the period since the prior assessment and that the assessor is independent of the system owner.

## Failure correction
- **Determination statement missing from assessment record** → reopen the assessment, document the gap, and reassess.
- **Other-than-satisfied finding without POA&M** → open a POA&M entry within 7 days, assign an owner, and notify the authorizing official.
- **Assessor independence violation** → reassign the assessment to an independent assessor, document the violation, and review the prior assessment for impact.

## Limitations
- NIST SP 800-53A Rev 5 defines the assessment procedure syntax; the depth and frequency of assessments depend on the organization's risk tolerance and authorization timeline.
- An other-than-satisfied determination may be acceptable under documented compensating controls; assessors should document the rationale.
- Automated assessment tooling should not replace human judgment for nuanced controls (e.g., organizational policy awareness).

## Scope note
This article is part of the templates leaf. Cross-reference: NIST_SP_800_53_REV5_CONTROL_TEMPLATES_GOVERNANCE.md, ISO_15489_RECORDS_MANAGEMENT_GOVERNANCE.md, NIST_SP_800_37_RISK_MANAGEMENT_FRAMEWORK_TEMPLATE_GOVERNANCE.md.

## Canonical sources
- NIST SP 800-53A Rev 5 — Assessing Security and Privacy Controls in Information Systems and Organizations: https://csrc.nist.gov/publications/detail/sp/800-53a/rev-5/final
- NIST SP 800-53 Rev 5 — Security and Privacy Controls for Information Systems and Organizations: https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final
- NIST SP 800-37 Rev 2 — Risk Management Framework for Information Systems and Organizations: https://csrc.nist.gov/publications/detail/sp/800-37/rev-2/final
- NIST SP 800-137A — Managing Information Security Continuous Monitoring (ISCM) Programs: https://csrc.nist.gov/publications/detail/sp/800-137a/final
- NIST SP 800-161 Rev 1 — Cybersecurity Supply Chain Risk Management Practices: https://csrc.nist.gov/publications/detail/sp/800-161/rev-1/final