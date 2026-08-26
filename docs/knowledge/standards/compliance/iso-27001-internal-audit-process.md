# iso-27001-internal-audit-process

**Issue:** Running ISO 27001 Clause 9.2 internal audits to maintain certification readiness
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
ISO 27001 Clause 9.2 requires internal audits at planned intervals to verify that the ISMS conforms to requirements and is effectively implemented. Many organizations treat this as a checkbox rather than a useful assurance tool.

## Pattern / Solution
Annual internal audit program:

1. Audit plan (created at start of year):
   - Scope of each audit cycle
   - Schedule and frequency (at minimum annually; high-risk areas more frequently)
   - Auditor assignments (independent of area being audited)

2. Audit checklist template:
   - Clause-by-clause conformance (Clauses 4-10)
   - Annex A controls sampled based on risk (focus on high-risk controls)
   - Evidence requested per control

3. Audit execution:
   - Document review (policies, procedures, records)
   - Interview control owners
   - Technical testing (spot-check configurations, access logs)

4. Findings classification:
   - Major nonconformity: ISMS requirement not met or control completely absent
   - Minor nonconformity: isolated failure; ISMS requirement generally met
   - Observation: improvement opportunity (no nonconformity)

5. Audit report and corrective action:
   - Issue findings to management within 5 business days
   - Root cause analysis for each nonconformity
   - Corrective action plan with owner and due date
   - Follow-up audit to verify closure

Auditor competence: internal auditors must complete ISO 27001 lead auditor training or demonstrate equivalent competence.

## Gotchas
- Self-auditing (area head auditing own area) is a major finding at certification audit
- Corrective actions must address root cause, not just symptoms
- Certification body will review internal audit records — gaps in coverage raise questions
- Internal audit reports are confidential legal documents — define retention policy

## Related
- `iso-27001-management-review.md`
- `iso-27001-isms-scope-definition.md`
