# hipaa-administrative-safeguards

**Issue:** Implementing HIPAA Security Rule administrative safeguards (45 CFR 164.308)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Administrative safeguards are the largest HIPAA Security Rule category (9 required standards). They govern policies, procedures, workforce training, and risk management for ePHI protection.

## Pattern / Solution
Required administrative safeguard standards:

1. Security Management Process (164.308(a)(1)):
   - Annual risk analysis: identify ePHI threats, vulnerabilities, likelihood, and impact
   - Risk management plan: implement security measures to reduce risk to reasonable and appropriate level
   - Sanction policy: formal consequences for workforce violations
   - Information system activity review: audit log review procedures

2. Assigned Security Responsibility (164.308(a)(2)):
   - Designate a Security Officer; document name and contact

3. Workforce Security (164.308(a)(3)):
   - Access authorization: formal process for granting ePHI access
   - Access supervision and termination: revoke access on departure within 24 hours

4. Information Access Management (164.308(a)(4)):
   - Minimum necessary access (least privilege)
   - Access authorization and modification procedures
   - For clearinghouses: isolate ePHI from non-ePHI systems

5. Security Awareness and Training (164.308(a)(5)):
   - Workforce security awareness training (annual; document completion)
   - Procedures for guarding against malware
   - Monitoring log-in attempts and reporting discrepancies
   - Password management training

6. Security Incident Procedures (164.308(a)(6)):
   - Incident response and reporting procedures
   - Document all incidents including those determined to be non-breaches

7. Contingency Plan (164.308(a)(7)):
   - Data backup plan, disaster recovery plan, emergency mode operation plan
   - Testing and revision procedures; application criticality analysis

8. Evaluation (164.308(a)(8)):
   - Periodic technical and non-technical evaluation of security implementation

9. Business Associate Contracts (164.308(b)(1)):
   - Written BAA with all business associates before sharing ePHI

## Gotchas
- Risk analysis must be documented and updated annually — "we did it once" fails audits
- Training must be documented: names, dates, completion — verbal training is insufficient
- BAAs must cover all downstream subcontractors; chain of BAAs required
- Security incident reporting must capture minor incidents, not just breaches

## Related
- `hipaa-compliance.md`
- `hipaa-phi-handling.md`
- `hipaa-physical-safeguards.md`
