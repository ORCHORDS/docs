---
title: "EU AI Act Article 27 FRIA Version Guide"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Regulation (EU) 2024/1689 (EU AI Act); https://eur-lex.europa.eu/eli/reg/2024/1689/oj"
---

# EU AI Act Article 27 FRIA Version Guide

## Scope

Reference card for Article 27 of Regulation (EU) 2024/1689, *the AI Act*, which requires a Fundamental Rights Impact Assessment (FRIA) for certain high-risk AI systems before they are placed on the market or put into service. Profiles that govern high-risk AI deployments in the EU should reference Article 27 explicitly and bind the FRIA to the broader risk-management framework (ISO 31000:2018, ISO/IEC 23894:2023, NIST AI RMF).

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | Regulation (EU) 2024/1689 (EU AI Act) |
| Article | Article 27 (Fundamental Rights Impact Assessment for high-risk AI systems) |
| Status | Published (July 2024); entered into force August 2024; FRIA obligations applicable from 2 August 2026 (24 months after entry into force) |
| Companion | EU AI Act Articles 9 (risk-management system), 10 (data governance), 11 (technical documentation), 12 (record-keeping), 13 (transparency), 14 (human oversight), 15 (accuracy, robustness, cybersecurity) |
| Source URL | https://eur-lex.europa.eu/eli/reg/2024/1689/oj |

## Plan

1. Reference Article 27 by number and revision whenever a profile governs a high-risk AI deployment in the EU.
2. Determine whether the AI system is in the FRIA scope (Article 6(1) high-risk systems used by public bodies, private entities providing public services, or specified banking/insurance contexts).
3. Conduct the FRIA before the AI system is placed on the market or put into service.
4. Document the categories of natural persons and groups affected, the potential harms, the foreseeable misuse, the risks to fundamental rights, the existing mitigation measures, and the residual risks.
5. Notify the relevant market surveillance authority of the FRIA results.
6. Review and update the FRIA throughout the AI system lifecycle, especially when there are significant changes that may affect fundamental-rights risks.
7. Coordinate the FRIA with the data-protection impact assessment (DPIA) under GDPR where personal data is processed.

## Inputs

- AI Act Articles 6 (high-risk classification), 9 (risk-management system), 13 (transparency), 14 (human oversight), 26 (deployer obligations), 27 (FRIA).
- AI system description, intended purpose, scope of use, and the affected natural persons and groups.
- Existing DPIA, risk-management framework (ISO 31000), and AI risk-management framework (ISO/IEC 23894, NIST AI RMF).
- Internal stakeholder consultation records and legal review.

## ORCHORDS Profile

ORCHORDS treats Article 27 as a binding obligation for high-risk AI deployments in the EU. Profiles that reference Article 27 should identify the affected natural persons and groups, document the foreseeable misuse, and bind the FRIA to the broader risk-management framework. A profile that claims AI Act compliance without an Article 27 FRIA for in-scope systems is non-conformant.

Profiles that govern AI deployments outside the EU should still bind to ISO/IEC 23894:2023 and NIST AI RMF as the cross-jurisdiction baseline.

## Implementation Notes

- FRIA obligations apply from 2 August 2026. Deployers with high-risk AI systems in operation before that date should complete the FRIA before the date applies.
- The FRIA is distinct from the DPIA under GDPR; both may be required for the same AI system. Coordinate the documents rather than duplicating them.
- Foreseeable misuse is a normative requirement: identify the misuse scenarios that are reasonably foreseeable, not only the intended use.
- Notification to the market surveillance authority is required. Maintain the notification record alongside the FRIA.
- Review and update the FRIA at significant changes; an annual review cadence is a defensible baseline.

## Companion Documents

- [EU AI Act 2024/1689 Version Guide](EU_AI_ACT_2024_1689_VERSION_GUIDE.md)
- [ISO/IEC 42001:2023 AIMS Version Guide](ISO_IEC_42001_2023_AIMS_VERSION_GUIDE.md)
- [ISO/IEC 23894:2023 AI Risk Version Guide](ISO_IEC_23894_2023_AI_RISK_VERSION_GUIDE.md)
- [ISO/IEC 42005 AI Impact Assessment Version Guide](ISO_IEC_42005_AI_IMPACT_ASSESSMENT_VERSION_GUIDE.md)
- [NIST AI 600-1 GenAI Profile Version Guide](NIST_AI_600_1_GENAI_PROFILE_VERSION_GUIDE.md)
- [NIST AI 100-2 Adversarial ML Version Guide](NIST_AI_100_2_ADVERSARIAL_ML_VERSION_GUIDE.md)
- [MITRE ATLAS Version Guide](MITRE_ATLAS_VERSION_GUIDE.md)
- [OECD AI Principles 2024 Version Guide](OECD_AI_PRINCIPLES_2024_VERSION_GUIDE.md)
- [UNESCO AI Ethics 2021 Version Guide](UNESCO_AI_ETHICS_2021_VERSION_GUIDE.md)
- [C2PA Content Credentials Version Guide](C2PA_CONTENT_CREDENTIALS_VERSION_GUIDE.md)
