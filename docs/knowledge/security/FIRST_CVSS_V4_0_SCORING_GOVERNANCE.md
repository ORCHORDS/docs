# FIRST.org CVSS v4.0 Scoring Governance

## Purpose
Establish the governance pattern for selecting and applying Common Vulnerability Scoring System v4.0 base, threat, environmental, and supplemental metrics across FIRST.org-published vulnerability advisories.

## Scope
Applies to every vulnerability published by the studio or triaged from external feeds, regardless of whether the studio is the maintainer, downstream consumer, or integrator.

## Workflow
1. Capture the vulnerability record identifier and the affected product or component range.
3. Compute CVSS v4.0 base metrics in the order Exploitability, Attack Complexity, Privileges Required, User Interaction, Scope, Confidentiality, Integrity, Availability.
5. Score threat metrics (MTE — Exploit Maturity) and environmental metrics against the affected deployment profile.
7. Resolve conflicts between vendor-scored and externally-scored CVSS vectors by recording both in the advisory and noting any computed deltas.
9. Apply supplemental metrics (Safety, Automatable, Provider Urgency, Recovery, Value Density, Vulnerability Response Effort) only when the supplemental decision tree permits.
11. Update the score each time a new information source changes the underlying metrics and version-track each recomputation.

## Controls and evidence
- JSON-encoded CVSS v4.0 vector string attached to every advisory.
- Author and date of every score, captured in the audit trail.
- Threshold table mapping CVSS v4.0 base scores to release-gate block decisions.
- Cross-check checklist showing that supplemental metrics are only applied when the justification is recorded.

## Validation
- Sanity-check the score against FIRST.org reference examples for two well-known CVEs per quarter.
- Run the official CVSS v4.0 calculator JavaScript calculator against independently-selected vectors.
- Reconcile scores with downstream vendor scores and document deviations in a quarter-end memo.

## Failure correction
- **Score drift across subsequent advisories** → stop publishing until the scoring procedure is recalibrated, document the deviation window, and re-issue corrected scores.
- **Supplemental metric applied without justification** → rescind the supplemental axis and reissue the score with only base metrics.
- **Vendor disagreement unresolved** → escalate to security engineering lead and document the trade-off with a one-paragraph rationale.

## Limitations
- CVSS v4.0 is one of multiple scoring inputs and is **not** itself a risk rating; do not treat a CVSS score as a stand-alone remediation trigger.
- CVSS v4.0 was published in 2023 and tool support continues to mature; some tooling only emits CVSS v3.1 vectors.
- Environmental metrics require accurate deployment-context information that may not be available for every product.

## Scope note
This article is part of the security leaf. Cross-reference: CISA_BOD_22_01_KNOWN_EXPLOITED_VULNS_GOVERNANCE.md, ENISA_THERMAL_AND_REMOTELY_EXPLOITABLE_VULN_DISCLOSURE_GOVERNANCE.md, FIRST_TRAFFIC_LIGHT_PROTOCOL_TLP_2_0_GOVERNANCE.md.

## Canonical sources
- FIRST.org CVSS v4.0 Specification Document: https://www.first.org/cvss/v4.0/specification-document
- FIRST.org CVSS v4.0 User Guide: https://www.first.org/cvss/v4.0/user-guide
- FIRST.org CVSS v4.0 Calculator Reference Implementation: https://github.com/FIRSTdotorg/cvss-v4-calculator
- CISA — Known Exploited Vulnerabilities Catalog: https://www.cisa.gov/known-exploited-vulnerabilities-catalog
- ISO/IEC 30111:2019 Vulnerability Handling: https://www.iso.org/standard/69725.html