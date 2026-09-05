---
title: "HIPAA Security Rule Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "45 CFR § 164.302–§ 164.318 (HIPAA Security Rule); https://www.hhs.gov/hipaa/for-professionals/security/"
---

# HIPAA Security Rule Governance

## Purpose

The HIPAA Security Rule (45 CFR Part 164, Subpart C) establishes the administrative, physical, and technical safeguards required of covered entities and business associates to protect the confidentiality, integrity, and availability of electronic protected health information (ePHI). It complements the HIPAA Privacy Rule (45 CFR Part 164, Subpart E). The HIPAA Security Rule Notice of Proposed Rulemaking to update the Security Rule was published in December 2024 (proposed § 164.100–§ 164.114 revisions) but is not yet final as of the article date.

## Current context and source status

The current Security Rule text remains the 2013 Omnibus-era version (Subpart C, § 164.302–§ 164.318). NIST SP 800-66 Rev. 2 (Implementing the HIPAA Security Rule) is the implementation reference. The 2024 NPRM proposes moving from "addressable" to prescriptive controls; organisations should track the final rule.

## Governance workflow and controls

1. Administrative safeguards (§ 164.308): security management (incl. risk analysis 164.308(a)(1)(ii)(A) and risk management (B)), workforce security, information access management, training, incident procedures (track with NIST SP 800-61 Rev. 2), contingency plan (164.308(a)(7)), evaluation, BAA management (164.308(b)).
2. Physical safeguards (§ 164.310): facility access controls, workstation use / device controls, device and media controls.
3. Technical safeguards (§ 164.312): access control, audit controls, integrity, person or entity authentication, transmission security.
4. Maintain the documentation requirements (§ 164.316): policies, procedures, action logs, risk-analysis updates (six-year retention).
5. Perform risk analysis on every workforce, system, or process change affecting ePHI; document risk management decisions.
6. Cross-reference OCR (Office for Civil Rights) enforcement rules on breach notification (45 CFR §§ 164.400–414) and to the FTC Safeguards Rule where applicable (GLBA scope overlap).

## Validation and evidence

- Most-recent (within calendar year) HIPAA Security Risk Assessment with sign-off by the security official.
- Policies and procedures (administrative, physical, technical) maintained current and version-stamped.
- Workforce training records and sanctions policy execution evidence.
- Contingency plan, data backup plan, emergency mode operation, disaster recovery plan (§ 164.308(a)(7)).
- BAA inventory for every business associate with downstream BAAs where subcontractor principle applies.

## Failure correction

Common defects include stale risk analyses, treating "addressable" as "optional", and missing BAA enforcement. Corrective actions include a risk-assessment refresh per change, addressing all addressable specifications with documented rationale (implement / alternative / not applicable), and continuous BAA enforcement.

## Limitations

- The Security Rule is sectoral (US covered entity / business associate scope); non-covered entities are not directly bound.
- The forthcoming NPRM update is widely expected to harden prescriptive requirements; align to NIST SP 800-66 Rev. 2 mapped to SP 800-53 Rev. 5 for forward-compatibility.
- The Breach Notification Rule (45 CFR §§ 164.400–414) is separate but operationally interlocked.

## Canonical sources

- 45 CFR Part 164, Subpart C (HIPAA Security Rule).
- 45 CFR Part 164, Subpart E (HIPAA Privacy Rule).
- 45 CFR §§ 164.400–414 (Breach Notification Rule).
- NIST SP 800-66 Rev. 2 (HIPAA Security Rule implementation).
- HHS / OCR guidance documents.

## Scope note

This article belongs to the standards leaf and cross-references the engineering leaf for technical safeguard implementation, the legal/compliance leaf for BAA / breach notifications, and the risk leaf for ePHI risk analysis.
