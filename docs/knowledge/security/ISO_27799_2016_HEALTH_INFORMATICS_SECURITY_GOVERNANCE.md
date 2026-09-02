# ISO 27799:2016 Health Informatics Security Governance

## Purpose

Govern the application of ISO 27799:2016 (health informatics — information security management in health using ISO/IEC 27002) so that health information receives its required protections: the standard tailors ISO/IEC 27002's controls to healthcare's specific risks — clinical safety consequences, sensitive personal data, and complex multi-party care delivery.

## Scope

Applies to studio systems that store, process, or transmit health information. Covers the healthcare control tailoring, health-data-specific safeguards, and continuity requirements the standard adds. Does not cover the ISMS itself (ISO/IEC 27001 governs that) or jurisdictional health privacy law.

## Workflow

1. Determine applicability precisely: which data qualifies as health information (patient records, clinical data, derived health metrics) and which systems touch it; the tailoring applies to that set.
2. Apply the 27099-tailored control set: implement ISO/IEC 27002 controls with the health-sector guidance — access control reflecting care relationships, availability reflecting clinical dependence, and integrity reflecting diagnosis impact.
3. Prioritize availability and integrity per healthcare's risk profile: unavailable or corrupted health information creates clinical safety risk beyond ordinary data-loss economics; continuity planning treats restoration as a patient-safety function.
4. Control multi-party access deliberately: care delivery spans organizations (providers, labs, insurers); the standard's guidance on inter-organizational access and information exchange governs those flows.
5. Manage patient identity carefully: misidentification is a patient-safety event, not merely a privacy failure; identity controls get the rigor safety consequences demand.
6. Audit health information access: access logging and review per the standard's monitoring guidance — health data access is a high-sensitivity audit domain.
7. Integrate with health privacy law: HIPAA, GDPR health data provisions, or national health records regimes layer legal requirements on the standard's control base; both apply.

## Controls and evidence

- Health information scope determination (data and systems).
- Tailored control implementation records mapped to ISO 27799 guidance.
- Continuity plans reflecting clinical restoration priorities.
- Multi-party access flow documentation with controls.
- Access logging and review records.
- Legal-regime integration notes.

## Validation

- Sample five tailored controls and confirm implementation reflects the health-sector guidance, not generic 27002 text.
- Confirm access review runs on the health-data audit domain at the standard's cadence.
- Confirm continuity plans exist for systems whose outage has clinical consequences.

## Failure correction

- **Generic controls applied without health tailoring** → re-apply with the sector guidance; generic implementation misses the clinical risk profile.
- **Access review gaps on health data** → restore review cadence and investigate the missed period for inappropriate access.
- **Continuity plan absent for clinical system** → build the plan with clinical input on restoration priorities.

## Limitations

- ISO 27799 tailors 27002:2013-era controls; organizations on 27002:2022 control structure map controls across editions deliberately.
- The standard does not replace health privacy law or clinical safety standards; it secures information within that ecosystem.
- Editions age; track ISO health informatics technical committee work for revisions.

## Scope note

This article is part of the security leaf. Cross-reference: `ISO_IEC_27701_2019_PII_PROCESSOR_CONTROLS_GOVERNANCE.md` (standards leaf), `ISO_IEC_29134_2023_PRIVACY_IMPACT_ASSESSMENT_APPLICATION_GOVERNANCE.md` (standards leaf), and `BUSINESS_CONTINUITY_MANAGEMENT_SYSTEM.md` (business leaf).

## Canonical sources

- ISO 27799:2016 — Health informatics — Information security management in health using ISO/IEC 27002: https://www.iso.org/obp/ui/#iso:std:iso:27799:ed-2
- ISO/IEC 27002 — Information security controls: https://www.iso.org/obp/ui/#iso:std:iso-iec:27002:ed-4
- ISO 27799 and ISO/TC 215 — Health informatics: https://www.iso.org/committee/54960.html
- NIST SP 800-66 Rev 2 — Implementing HIPAA Security Rule: https://csrc.nist.gov/pubs/sp/800/66/r2/final
- ENISA — Healthcare security guidance: https://www.enisa.europa.eu/
