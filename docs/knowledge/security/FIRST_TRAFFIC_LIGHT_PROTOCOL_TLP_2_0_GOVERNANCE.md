# FIRST.org Traffic Light Protocol TLP 2.0 Governance

## Purpose
Establish the governance pattern for selecting, applying, and recording Traffic Light Protocol (TLP) 2.0 markings across every information exchange in which the studio is a sender, recipient, or intermediary.

## Scope
Applies to every artefact the studio creates, modifies, transmits, or receives in the context of vulnerability disclosure, incident response, threat intelligence sharing, and CSIRT/CSIRT-equivalent coordination.

## Workflow
1. Apply a TLP marking to every artefact at the time of creation; the marking is binding regardless of the channel of distribution.
3. Recognise the four TLP 2.0 markings (TLP:RED, TLP:AMBER, TLP:AMBER+STRICT, TLP:GREEN, TLP:CLEAR) and the corresponding sharing boundaries.
5. When forwarding information to a third party, retain the original TLP marking; do not reclassify without the originator's authorisation.
7. Record every redistribution decision in the audit log, including recipient, date, channel, and rationale.
9. When in doubt about the appropriate marking, default to the more restrictive marking and request clarification from the originator.

## Controls and evidence
- TLP marking policy keyed to artefact type and disclosure context.
- Distribution audit log with artefact identifier, TLP marking, recipient, channel, date, and reclassification rationale.
- TLP handling training record per team member.
- Quarterly reconciliation between artefacts distributed and artefacts in the audit log.

## Validation
- Sample-audit five artefacts, confirm the marking is present, consistent with the artefact content, and matches the audit log entry.
- Verify that recipients identified for TLP:AMBER+STRICT are limited to participating organisations.
- Confirm training records are current within the last 12 months for every team member handling TLP-marked artefacts.

## Failure correction
- **Marking missing from an artefact** → treat the artefact as TLP:AMBER+STRICT until originator clarification is received, document the incident, and retrain the responsible party.
- **Reclassification without originator authorisation** → recall the reclassified artefact, document the incident, and reissue under the original marking.
- **Audit log entry missing** → reconstruct the entry from available evidence, document the gap, and update the recording procedure.

## Limitations
- TLP 2.0 is a community standard and not a legal instrument; it cannot override contractual or regulatory disclosure obligations.
- TLP 2.0 markings are honoured within the FIRST.org community; not all external parties observe TLP markings.
- Some jurisdictions impose their own information classification rules that may be more restrictive than TLP.

## Scope note
This article is part of the security leaf. Cross-reference: ENISA_THERMAL_AND_REMOTELY_EXPLOITABLE_VULN_DISCLOSURE_GOVERNANCE.md, FIRST_CVSS_V4_0_SCORING_GOVERNANCE.md, NIST_SP_800_61_R3_INCIDENT_LEGAL_COORDINATION_GOVERNANCE.md.

## Canonical sources
- FIRST.org Traffic Light Protocol (TLP) 2.0: https://www.first.org/tlp/
- FIRST.org TLP 2.0 Frequently Asked Questions: https://www.first.org/tlp/faq
- ENISA — Information Sharing and Analysis Centres (ISACs): https://www.enisa.europa.eu/topics/national-cyber-security-strategies
- NIST SP 800-150 (Guide to Cyber Threat Information Sharing): https://csrc.nist.gov/pubs/sp/800/150/final
- ISO/IEC 27010:2015 (Information security management for inter-sector and inter-organisational communications): https://www.iso.org/standard/68434.html