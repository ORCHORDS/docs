---
title: "GLBA Safeguards Rule Governance"
owner: "Standards Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "16 CFR Part 314 (Standards for Safeguarding Customer Information); https://www.ftc.gov/business-guidance/resources/financial-institutions-or-affiliates-ftc-standards-safeguarding-customer-information"
---

# GLBA Safeguards Rule Governance

## Purpose

The Gramm-Leach-Bliley Act (GLBA) Safeguards Rule (16 CFR Part 314) requires financial institutions under FTC jurisdiction to develop, implement, and maintain a comprehensive information security program to protect the security, confidentiality, and integrity of customer information. The 2021 amendments (effective 2022/2023) introduced specific elements: designated qualified individual, written incident response plan, multi-factor authentication, encryption, access controls, inventory of customer information, continuous monitoring, and annual reporting to the board / equivalent governing body.

## Current context and source status

The current Safeguards Rule is the 16 CFR Part 314 as amended in 2021. Further amendments (e.g., proposed notification supplement) are tracked separately; as of the article date the core Rule is in force and FTC enforcement actions are active.

## Governance workflow and controls

1. Designate a Qualified Individual (QI) responsible for the information security program (§ 314.4(a)).
2. Conduct a risk assessment (§ 314.4(b)) covering customer-information flows, third-party access, and disposal.
3. Implement the 11 controls (§ 314.4(c) and § 314.4(d)–(j) where applicable): access controls (incl. MFA), data inventory, encryption (in transit and at rest), secure development practices for in-scope applications, multi-factor authentication for individuals accessing customer information, disposal procedures, change management, monitoring, continuous monitoring, training, service-provider oversight.
4. Implement an incident response plan (§ 314.4(g)) that addresses: internal response, remediation, notification (aligned to state breach-notification rules and, where applicable, the FTC's notification supplement).
5. Maintain a written information security plan (§ 314.3) reviewed at least annually and within the no-later-than 30-days trigger for material changes.
6. Annual report to the board / governing body, sign-off by the QI (§ 314.4(j)).
7. Service-provider oversight (§ 314.4(i)): due diligence, contractual safeguards, periodic assessments.

## Validation and evidence

- Current written information security plan with version stamp and review date.
- Annual QI report to the board / governing body.
- Risk assessment with documented treatment of findings.
- Multi-factor authentication scope map and exception register.
- Service-provider inventory and assessment evidence.

## Failure correction

Common defects include a stale risk assessment, MFA coverage gaps for administrative / privileged access, missing third-party service-provider oversight, and missed annual board reporting. Corrective actions include a written-plan refresh cycle, MFA policy review, and a service-provider contract-update programme.

## Limitations

- The Safeguards Rule applies to "financial institutions" under FTC jurisdiction. GLBA-tied depository institutions follow the interagency Safeguards Rule (12 CFR Part 30, Appendix B) and not 16 CFR Part 314.
- The Rule is sectoral; it does not override state breach-notification statutes (CCPA, NYDFS, etc.), which may impose faster notification timelines or stricter content requirements.
- The notification supplement (proposed in 2024) would, if finalised, layer additional notification obligations on to the Rule.

## Canonical sources

- 16 CFR Part 314 (FTC Safeguards Rule).
- 12 CFR Part 30, Appendix B (FFIEC-aligned Safeguards Rule for depository institutions).
- FTC Safeguards Rule guidance documents and FAQs.
- NIST SP 800-171 / SP 800-53 Rev. 5 cross-mapping for layered compliance.

## Scope note

This article belongs to the standards leaf and cross-references the engineering leaf for control implementation, the operations leaf for monitoring cadences, and the legal/compliance leaf for service-provider / BAA contracts and breach notification.
