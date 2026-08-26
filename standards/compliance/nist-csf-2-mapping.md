# nist-csf-2-mapping

**Issue:** Mapping security controls to NIST Cybersecurity Framework 2.0 (February 2024)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
NIST CSF 2.0 expanded from 5 to 6 functions, added supply chain focus, and introduced implementation tiers and profiles. Organizations use it to communicate security posture and prioritize investments.

## Pattern / Solution
CSF 2.0 Six Functions:

GOVERN (new):
- GV.OC: Organizational Context — document risk tolerance; identify legal/regulatory requirements
- GV.RM: Risk Management Strategy — risk appetite statement approved by board
- GV.SC: Cybersecurity Supply Chain Risk Management — supplier risk assessments; SBOM for software

IDENTIFY:
- ID.AM: Asset Management — maintain asset inventory; classify by criticality
- ID.RA: Risk Assessment — threat modeling; vulnerability assessments

PROTECT:
- PR.AA: Identity Management, Auth, and Access Control — MFA; least privilege; PAM
- PR.DS: Data Security — encryption, DLP, secure deletion
- PR.PS: Platform Security — hardening, patching, configuration management

DETECT:
- DE.CM: Continuous Monitoring — SIEM; IDS; anomaly detection

RESPOND:
- RS.MA: Incident Management — documented IRP; tabletop exercises
- RS.CO: Incident Response Reporting — notify stakeholders; regulatory notifications

RECOVER:
- RC.RP: Incident Recovery Plan — tested RTO/RPO; DR exercises

Implementation tiers (1-4):
- Tier 1 Partial: ad hoc, reactive
- Tier 2 Risk Informed: some policies; not org-wide
- Tier 3 Repeatable: formalized; risk-based decisions
- Tier 4 Adaptive: continuous improvement; threat intel integrated

Target profile: document current tier per function; set target tier; create gap remediation plan.

## Gotchas
- CSF is a framework, not a certification — no official auditor certification program
- CSF 2.0 tiers apply per function, not globally
- CSF 1.1 mappings do not directly apply to 2.0 — re-map controls
- Board reporting: use CSF language to communicate risk posture to non-technical leadership

## Related
- `nist-800-53-control-families.md`
- `iso-27001-risk-assessment-methodology.md`
