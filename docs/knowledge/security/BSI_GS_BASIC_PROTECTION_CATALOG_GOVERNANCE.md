# BSI IT-Grundschutz (GS) Basic Protection Catalog Governance

## Purpose
Establish the governance pattern for aligning the studio's information security controls with the German Federal Office for Information Security (BSI) IT-Grundschutz (GS) basic protection catalog.

## Scope
Applies to deployments in Germany, services delivered to German public-sector clients, and any organisation seeking BSI GS basic protection alignment as a baseline for assurance review.

## Workflow
1. Identify the BSI GS basic protection modules relevant to the studio's services and infrastructure; record the BSI module identifier and version.
3. Build a control mapping table that pairs each BSI GS basic protection requirement with the studio's existing policy or technical control.
5. For requirements not yet met, draft a remediation plan with owner, target date, and acceptance criteria.
7. Maintain an evidence repository containing configuration exports, audit logs, change records, and training records.
9. Reassess the alignment annually, when BSI GS basic protection catalog receives a significant update, or when the studio's scope changes.

## Controls and evidence
- Module applicability register with BSI GS basic protection module identifier, scope statement, and version.
- Control mapping table linking BSI GS basic protection requirements to internal policies or technical controls.
- Evidence repository with hash-signed manifest for integrity.
- Annual reassessment report with deviations, remediation plans, and lessons learned.

## Validation
- Sample-audit 10 randomly-selected BSI GS basic protection requirements and verify the evidence repository contains current and traceable evidence.
- Recompute the alignment coverage and reconcile with the previous year; investigate any unplanned regression.
- Confirm the evidence repository manifest hash matches the hash stored in the studio's content-addressed store.

## Failure correction
- **Alignment regression in a critical module** → escalate to the CISO, document compensating controls, and produce a recovery plan within 10 business days.
- **Evidence repository integrity failure** → restore from backup, document the incident, and re-validate all hashes.
- **BSI GS basic protection mapping missing** → assign an owner, document the mapping within 14 days, and add to the next annual reassessment.

## Limitations
- BSI GS basic protection is one of multiple cybersecurity frameworks; it does not by itself provide assurance of compliance with sector-specific requirements.
- BSI GS basic protection modules evolve over time; always reference the latest published edition.
- The pattern is a governance skeleton; organisations pursuing ISO 27001 certification on the basis of IT-Grundschutz should follow BSI's official cross-mapping.

## Scope note
This article is part of the security leaf. Cross-reference: NIST_SP_800_218A_SSDF_TAGGING_GOVERNANCE.md, NIST_IR_8441_CYBERSUPPLY_CHAIN_RISK_GOVERNANCE.md, ISO_IEC_27035_3_2023_INCIDENT_RESPONSE_EXERCISES_GOVERNANCE.md.

## Canonical sources
- BSI IT-Grundschutz (in English): https://www.bsi.bund.de/EN/Themen/ITGrundschutz/itgrundschutz_node.html
- BSI IT-Grundschutz-Kompendium (in German): https://www.bsi.bund.de/SharedDocs/Downloads/DE/BSI/Grundschutz/Kompendium/IT_Grundschutz_Kompendium_Edition2023.pdf
- BSI — Standard 200-1 (Information Security Management Systems): https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/Standards/standard_200-1.pdf
- BSI — Standard 200-2 (IT-Grundschutz Methodology): https://www.bsi.bund.de/SharedDocs/Downloads/EN/BSI/Standards/standard_200-2.pdf
- ISO/IEC 27001:2022 — Information security management systems — Requirements: https://www.iso.org/standard/27001