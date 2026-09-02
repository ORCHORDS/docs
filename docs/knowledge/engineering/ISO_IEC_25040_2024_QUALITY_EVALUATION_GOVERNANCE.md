# ISO/IEC 25040:2024 Quality Evaluation Module Governance

## Purpose

ISO/IEC 25040:2024, "Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — Quality evaluation guide," updates the evaluation guide in the SQuaRE family to provide practical guidance for planning, executing, and reporting quality evaluations of software and system products using the SQuaRE standards. This article governs how engineering teams use ISO/IEC 25040 to plan and conduct quality evaluations so that evaluation activities produce reliable, repeatable quality evidence.

## Scope

The standard applies to the evaluation of software and system products. Within this knowledge base, the article covers the selection of quality characteristics (from ISO/IEC 25010), the selection of evaluation methods, the use of quality measures (from ISO/IEC 25021-25024), the evaluation process (planning, executing, concluding), and the documentation of evaluation results. It does not cover the detailed measurement definitions; readers should consult the corresponding measure standards.

## Workflow

1. Establish the purpose of the evaluation: confirm what the evaluation must support (release decision, vendor selection, conformance claim, risk acceptance).
2. Select the quality characteristics to be evaluated from the ISO/IEC 25010 model appropriate to the product type. Each characteristic should be tied to a stakeholder concern.
3. Choose the quality measures for each selected characteristic from the ISO/IEC 25021-25024 standards or other authoritative sources. Each measure should have a defined measurement method, units, and scale.
4. Define the evaluation criteria: thresholds for acceptance, the decision rule (does any characteristic failure block release?), and the aggregation rule (how multiple measures are combined).
5. Plan the evaluation: select the sample, identify the evaluation environment, schedule the evaluation activities, identify the resources, and document the plan.
6. Execute the evaluation: take the measurements, record the data, and produce the evaluation records.
7. Conclude the evaluation: aggregate the measurements, apply the decision rule, and produce the evaluation report.

## Controls and evidence

Evaluation evidence includes the evaluation plan, the measurement records, the evaluation report, and the decision rule application. Each measurement should be repeatable: the method is documented, the environment is documented, the data are captured, and the result is reproducible. The evaluation report should clearly state which quality characteristics were evaluated, which measures were used, which thresholds were applied, and the resulting decision.

## Validation

Validation should confirm the evaluation purpose is documented, the selected quality characteristics match the purpose, the measures are appropriate to the characteristics, the evaluation was conducted by qualified evaluators following the documented plan, and the report supports the decision that was made. Repeatability checks (independent re-measurement on a sub-sample) strengthen validation.

## Failure correction

Common failure modes: evaluation is treated as a checkbox and produces no useful data (corrective: define a decision rule and require that the evaluation report either supports or blocks the decision); measures are chosen without consideration of validity (corrective: document each measure's validity for the characteristic being evaluated); evaluation environment differs from production (corrective: record environment differences and assess their impact); evaluation is not re-run after material changes (corrective: re-evaluate on material changes and document the trigger).

## Limitations

ISO/IEC 25040 guides the application of the SQuaRE family; it does not define the quality measures themselves. The standard assumes that the project has selected appropriate characteristics and measures; the choice of characteristic is half the evaluation. The standard does not address evaluations that require specific expertise (e.g., security testing, formal verification) — those are governed by their own standards.

## Scope note

This article summarizes project-neutral engineering use of ISO/IEC 25040:2024. It does not assert any specific evaluation outcome or claim any product conformance.

## Canonical sources

- ISO/IEC 25040:2024 — Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — Quality evaluation guide: https://www.iso.org/standard/85410.html
- ISO/IEC 25010:2011 — Systems and software engineering — Systems and software Quality Requirements and Evaluation (SQuaRE) — System and software quality models: https://www.iso.org/standard/35733.html