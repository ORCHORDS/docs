# ISO/IEC 25019:2023 Quality-in-Use Model Governance

## Purpose

ISO/IEC 25019:2023, *Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — Quality-in-use model*, defines quality-in-use characteristics — the outcome quality a user experiences when using a system in a real context of use — complementing ISO/IEC 25010's product quality model with a user-outcome perspective.

Product teams should apply the 25019 model so that quality requirements address what users achieve and experience (effectiveness, efficiency, freedom from risk, satisfaction characteristics) rather than only internal product properties.

## Scope

Applies to the studio's quality requirement definition and evaluation practice for user-facing systems. Covers the quality-in-use characteristics, their decomposition, and measurement orientation. Does not cover 25010's product quality characteristics or evaluation process (25040).

## Workflow

1. Distinguish the two models' roles: 25010 describes product properties (functional suitability, performance efficiency, reliability...); 25019 describes use outcomes — requirements should reference the model that matches the quality claim being made.
2. Express user-outcome requirements through the 25019 characteristics: effectiveness, efficiency, satisfaction, freedom from risk, and context coverage — each decomposed into sub-characteristics per the standard.
3. Bind quality-in-use requirements to contexts of use: a quality-in-use characteristic is meaningful only against specified users, tasks, and environments; context-free quality-in-use requirements are aspirational statements.
4. Measure quality-in-use empirically: usability testing, field analytics, task success measurement — the model's outcomes are observed in use, not derived from product inspection.
5. Trace quality-in-use requirements to product quality requirements: the causal chain runs from use outcomes to the product properties that deliver them; 25019 requirements without supporting 25010 properties are unactionable wishes.
6. Evaluate against defined targets: each quality-in-use measure has a target value and context, and evaluation reports measure against those targets.
7. Revisit contexts as they change: user populations, task mixes, and environments drift; quality-in-use evaluations are re-scoped when context shifts materially.

## Controls and evidence

- Quality-in-use requirement records with characteristics and context bindings.
- Context of use specifications per evaluation.
- Empirical measurement records (usability tests, field data) with methods.
- Trace links from quality-in-use requirements to product quality requirements.
- Evaluation reports with target comparisons.

## Validation

- Sample three quality-in-use requirements and confirm each names a 25019 characteristic and a context of use.
- Confirm the sample's measures come from empirical use observation, not product inspection alone.
- Confirm trace links land on product requirements with owners.

## Failure correction

- **Quality-in-use requirement without context** → specify users, tasks, and environments or reclassify as a product requirement.
- **Outcome claimed without empirical measurement** → schedule the measurement; unmeasured outcome claims are removed from evaluation reports.
- **No trace to product properties** → build the causal chain to actionable product requirements or drop the requirement.

## Limitations

25019 is the newest SQuaRE model addition (2023); measurement guidance and industry familiarity lag the established 25010 model. Quality-in-use measurement requires access to users and real contexts — earlier proxies (expert review) approximate but do not substitute.

## Scope note

This article is part of the engineering leaf. Cross-reference: `ISO_IEC_25010_2011_SOFTWARE_PRODUCT_QUALITY_MODEL.md`, `ISO_IEC_25040_2024_QUALITY_EVALUATION_GOVERNANCE.md`, and `W3C_WCAG_2_2_CONFORMANCE_MODEL.md`.

## Canonical sources

- ISO/IEC 25019:2023 — SQuaRE — Quality-in-use model: https://www.iso.org/obp/ui/#iso:std:iso-iec:25019:ed-1
- ISO/IEC 25010:2011 — SQuaRE — System and software quality models: https://www.iso.org/obp/ui/#iso:std:iso-iec:25010:ed-1
- ISO/IEC 25040 — SQuaRE — Evaluation process: https://www.iso.org/obp/ui/#iso:std:iso-iec:25040
- ISO 9241-110 — Ergonomics of human-system interaction — Interaction principles: https://www.iso.org/obp/ui/#iso:std:iso:9241:-110
- ISO 9241-11 — Usability: Concepts and terminology (context-of-use foundations): https://www.iso.org/obp/ui/#iso:std:iso:9241:-11
