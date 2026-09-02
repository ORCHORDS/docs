# ENISA Threat Landscape Annual Assessment Governance

## Purpose

Govern the studio's use of the ENISA Threat Landscape (ETL) annual publication so that external threat intelligence from an authoritative EU source is consumed systematically: threat trends reviewed, studio-relevant threats mapped to the threat model, and defensive priorities adjusted — rather than the report being noted and filed.

## Scope

Applies to the studio's threat intelligence review cycle using the ENISA Threat Landscape and related ENISA publications. Covers annual review workflow, threat-to-context mapping, and defensive adjustment. Does not cover operational threat feeds or incident response.

## Workflow

1. Schedule the annual ETL review: each ETL edition (published annually, e.g., ETL 2025) enters the threat modelling calendar; the review owns a named accountable person.
2. Extract the ETL's threat taxonomy: the prime threats the edition identifies (ransomware, social engineering, data-related threats, availability threats, malware, information manipulation, supply chain attacks) with their reported trends.
3. Map each prime threat to studio context: exposure assessment per threat — attack surface relevance, current controls, residual risk — recorded as a mapping table.
4. Prioritize by mapped exposure: the ETL ranks threats globally, but the studio's rank differs; the mapping table, not the ETL's global ordering, drives local priority.
5. Adjust defenses in the planning cycle: prioritized threats feed security roadmap items (detection use cases, control investments, exercise scenarios).
6. Cross-reference related ENISA publications: sector threat landscapes and threat intelligence reports deepen specific areas where mapping shows high exposure.
7. Retain the year-over-year trace: each ETL edition's mapping preserved, so trend deltas (rising/falling local exposure) are visible across editions.

## Controls and evidence

- ETL review calendar entry with accountable owner.
- Threat-to-context mapping table per edition.
- Priority adjustments derived from the mapping.
- Roadmap traceability from prioritized threats to planned work.
- Year-over-year mapping archive.

## Validation

- Confirm the current ETL edition was reviewed within the committed window after publication.
- Sample five prime threats: confirm each has a mapping entry with exposure assessment and control reference.
- Confirm at least one roadmap or exercise adjustment traces to the latest mapping.

## Failure correction

- **Review missed or informal** → run the mapping immediately; informal "reading" without recorded mapping does not count as review.
- **Mapping entries without exposure assessment** → complete the assessment or mark the threat not-applicable with rationale.
- **Adjustments not traced** → connect prioritized threats to roadmap items retroactively and fix the planning intake.

## Limitations

- The ETL is EU-focused and annual; fast-moving threat developments need supplementary operational feeds.
- Global threat rankings are not local risk rankings; the mapping step is where the ETL becomes useful or remains trivia.
- ETL editions change taxonomy structure between years; year-over-year comparison requires taxonomy reconciliation.

## Scope note

This article is part of the security leaf. Cross-reference: `ENISA_THERMAL_AND_REMOTELY_EXPLOITABLE_VULN_DISCLOSURE_GOVERNANCE.md`, `MITRE_ATTACK_ENTERPRISE_DETECTION_AND_ENGINEERING_GOVERNANCE.md`, and `ITIL_4_MONITORING_AND_EVENT_MANAGEMENT_PRACTICE_GOVERNANCE.md` (operations leaf).

## Canonical sources

- ENISA — Threat Landscape (latest edition): https://www.enisa.europa.eu/topics/cyber-threats/threat-landscape
- ENISA — Threat Landscape publications archive: https://www.enisa.europa.eu/publications
- MITRE ATT&CK — Adversarial Tactics, Techniques, and Common Knowledge: https://attack.mitre.org/
- NIST SP 800-150 — Guide to Cyber Threat Information Sharing: https://csrc.nist.gov/publications/detail/sp/800-150/final
- FIRST — Threat intelligence sharing standards: https://www.first.org/
