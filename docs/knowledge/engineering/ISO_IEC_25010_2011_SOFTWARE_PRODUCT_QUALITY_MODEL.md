# ISO/IEC 25010:2011 Software Product Quality Model

## Purpose

ISO/IEC 25010:2011 ("Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — System and software quality models") defines the product quality model and quality-in-use model that replaced ISO/IEC 9126-1. It specifies eight product quality characteristics—functional suitability, performance efficiency, compatibility, usability, reliability, security, maintainability, and portability—each decomposed into subcharacteristics, giving engineering teams a shared vocabulary for stating, measuring, and evaluating non-functional requirements. This article summarizes project-neutral engineering use of the standard; it does not claim conformance or evaluation outcomes.

## Scope

ISO/IEC 25010 is the reference model for defining quality requirements and structuring quality evaluation. It applies to systems and software products across the life cycle: requirements definition, architecture evaluation, test planning, measurement program design, and acceptance criteria. It does not define how to achieve quality (that is the role of process standards such as IEEE 12207 and quality assurance practices), nor does it define specific metrics, thresholds, or measurement procedures—those live in the wider SQuaRE series, notably ISO/IEC 2502x (measurement) and ISO/IEC 2504x (evaluation).

Within the engineering knowledge base, this article covers:

- the eight product quality characteristics and their principal subcharacteristics;
- the quality-in-use model (effectiveness, efficiency, satisfaction, freedom from risk, context coverage);
- how to use the model to write measurable quality requirements;
- evaluation planning and evidence; and
- limitations: a vocabulary and decomposition model, not a benchmark, certification scheme, or process mandate.

## Workflow

A team adopting ISO/IEC 25010 should use it as the taxonomy for all non-functional requirements work. The generic workflow is:

1. Enumerate the eight characteristics early in requirements definition so quality concerns are addressed systematically rather than ad hoc.
2. For each characteristic, decide relevance to the product and record the decision, including explicit "not applicable" decisions with rationale.
3. Decompose relevant characteristics into subcharacteristics and select the specific quality attributes the product must satisfy:
   - functional suitability: functional completeness, correctness, appropriateness;
   - performance efficiency: time behavior, resource utilization, capacity;
   - compatibility: co-existence, interoperability;
   - usability: appropriateness recognizability, learnability, operability, user error protection, aesthetics, accessibility;
   - reliability: maturity, availability, fault tolerance, recoverability;
   - security: confidentiality, integrity, non-repudiation, accountability, authenticity;
   - maintainability: modularity, reusability, analysability, modifiability, testability;
   - portability: adaptability, installability, replaceability.
4. Write each selected attribute as a measurable requirement with an acceptance criterion and a measurement method.
5. Map test plans and measurement definitions to the selected characteristics so evaluation coverage is traceable.
6. At evaluation time, apply the quality-in-use model to judge outcomes in real contexts of use, not merely product properties.

## Controls and evidence

Using the model as a control mechanism produces structured, auditable evidence:

- a quality requirements register where each entry names its ISO/IEC 25010 characteristic and subcharacteristic;
- for each requirement: a measurable target, a measurement method, a measurement frequency or evaluation point, and a responsible owner;
- an evaluation plan referencing ISO/IEC 25040-style processes: establish evaluation requirements, specify, design, and conduct evaluation, then report results;
- traceability from each characteristic to the tests, inspections, analyses, or demonstrations that verify it;
- quality-in-use results collected from representative users in realistic contexts, covering effectiveness, efficiency, satisfaction, freedom from risk, and context coverage.

Because the model is a decomposition, it prevents the common failure where "quality" is treated as a single, unmeasurable property. Every leaf attribute must resolve to something observable.

## Validation

Validation that the model is applied correctly should include:

- checking that every non-functional requirement maps to exactly one characteristic and subcharacteristic, and that unmapped requirements are justified;
- confirming each quality requirement has a measurement method and threshold, rejecting statements like "the system shall be maintainable" without an operational definition;
- verifying evaluation coverage: each selected characteristic has at least one planned evaluation activity with recorded results;
- confirming quality-in-use evaluation uses realistic contexts and representative users rather than developer self-assessment;
- reviewing metrics definitions for consistency with the SQuaRE measurement series so results are comparable over time.

## Failure correction

Common failure modes the model exposes, and the corrective actions each implies:

- Treating security as a single checkbox—the corrective action is to decompose into confidentiality, integrity, non-repudiation, accountability, and authenticity, and state each separately.
- Writing unmeasurable requirements ("user-friendly", "fast")—the corrective action is to bind each to a subcharacteristic with an operational metric.
- Ignoring quality-in-use and judging only product properties—the corrective action is to schedule context-of-use evaluation with real users.
- Dropping characteristics silently as scope pressure grows—the corrective action is to record "not applicable" decisions with rationale so the omission is a decision, not an oversight.
- Measurement drift where metric definitions change mid-project—the corrective action is to version metric definitions and restate baselines when they change.

## Limitations

ISO/IEC 25010 is a descriptive model, not a normative benchmark. It does not tell you what "good" looks like numerically; thresholds must be set per product and context. The 2011 edition's product quality model does not include safety as a characteristic (safety is treated under quality-in-use "freedom from risk" and in domain-specific standards), and it predates widespread machine-learning systems, so characteristics such as statistical model behavior are not first-class. It does not replace evaluation methodology (ISO/IEC 25040), measurement (ISO/IEC 25020 series), security control catalogs (NIST SP 800-53, ISO/IEC 27001), or accessibility conformance (W3C WAI). Claiming alignment with the model demonstrates vocabulary and decomposition discipline, not that the product is high quality.

## Scope note

This article summarizes project-neutral engineering use of ISO/IEC 25010:2011. It does not claim implementation, conformity, evaluation, or certification outcomes for any specific software product or organization.

## Canonical sources

- ISO/IEC 25010:2011 — System and software quality models (ISO catalog): https://www.iso.org/standard/35733.html
- ISO/IEC 25010:2011 — IEEE adoption record (IEEE Xplore): https://standards.ieee.org/ieee/25010/6687/