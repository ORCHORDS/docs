# NCSC-UK Active Cyber Defence Knowledge Governance

## Purpose
Establish the governance pattern for selecting, integrating, and operating National Cyber Security Centre (United Kingdom) Active Cyber Defence (ACD) services — DMARC web check, Protective DNS, Web Check, Mail Check, Exercise in a Box — as knowledge artifacts within the studio's defensive posture documentation.

## Scope
Applies to UK-based deployments, deployments serving UK users, and any organisation using NCSC-UK ACD tooling for vulnerability discovery, awareness training, or supply-chain hardening.

## Workflow
1. Inventory every ACD service in use, the responsible owner, and the frequency at which results are reviewed.
3. Capture the report URL, scoring rubric, and remediation deadline recommended by each service.
5. Triage each finding into the studio's risk register with the NCSC-UK severity classification and the studio's classification side-by-side.
7. Document lessons from Exercise in a Box tabletop scenarios as updated runbooks; refresh those runbooks quarterly.
9. Track Protective DNS and DMARC policy changes against the published compliance profile and update mail authentication configurations accordingly.

## Controls and evidence
- Decision table mapping NCSC-UK ACD findings to severity classification with documented override conditions.
- Owner roster per service with on-call coverage and rotation cadence.
- Tabletop schedule with last completed exercise, lessons learned, and runbook diff reference.
- Mail authentication policy history (SPF/DKIM/DMARC) with version tags.

## Validation
- Recompute the score from the most recent NCSC-UK ACD scan, confirm that it has been reviewed within the last 30 days, and document any unaddressed findings.
- Verify that the Protective DNS resolvers in use are still on the NCSC-UK recommended list.
- Confirm that DMARC reports are being delivered to a monitored mailbox with weekly review.

## Failure correction
- **Findings exceeding 90 days without remediation** → escalate to the security steering group and document the compensating control or business acceptance decision.
- **Tabletop exercise skipped for two quarters** → close the participation gap, document the reason, and re-baseline the exercise cadence.
- **DMARC policy weakened** → investigate the cause, restore the policy, and publish a one-page post-mortem.

## Limitations
- ACD services are best-suited for UK-anchored organisations; non-UK deployments should not assume parity of threat intelligence.
- ACD scoring is not a substitute for a full third-party assurance review such as ISO/IEC 27001 or SOC 2.
- Some ACD services are available only to UK-registered entities; cross-border applicability is limited.

## Scope note
This article is part of the security leaf. Cross-reference: ENISA_THERMAL_AND_REMOTELY_EXPLOITABLE_VULN_DISCLOSURE_GOVERNANCE.md, FIRST_CVSS_V4_0_SCORING_GOVERNANCE.md, NIST_SP_800_61_R3_INCIDENT_LEGAL_COORDINATION_GOVERNANCE.md.

## Canonical sources
- NCSC-UK Active Cyber Defence overview: https://www.ncsc.gov.uk/section/active-cyber-defence
- NCSC-UK Protective DNS guidance: https://www.ncsc.gov.uk/collection/protective-domain-name-system
- NCSC-UK DMARC web check: https://www.ncsc.gov.uk/information/dmarc-web-check
- NCSC-UK Exercise in a Box: https://www.ncsc.gov.uk/information/exercise-in-a-box
- NCSC-UK Mail Check: https://www.ncsc.gov.uk/information/mail-check