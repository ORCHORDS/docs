# IEEE 16326:2023 Project Management Governance

## Purpose

IEEE 16326:2023, *Standard for Application of Project Management Processes for Systems and Software Engineering*, adapts project management practice to systems and software engineering contexts, aligned with ISO/IEC/IEEE 12207 and 15288 process frameworks, covering project planning, assessment, and control with software-specific considerations.

Teams running engineering projects should apply 16326's process model so planning and control mechanisms fit engineering work's iterative, estimation-heavy, and change-prone nature rather than generic project management templates.

## Scope

Applies to the studio's systems and software engineering projects. Covers project planning processes, project assessment and control, and measurement integration. Does not cover portfolio management or organizational governance of projects.

## Workflow

1. Plan per the standard's process model: project planning that produces work breakdown, schedules, and resource plans tied to the technical processes actually being used (12207 lifecycle processes), not generic phase templates.
2. Tailor deliberately: the standard expects tailoring to project size, criticality, and lifecycle model — record the tailoring decisions and their rationale per project.
3. Estimate with method and record error: engineering estimation (size, effort, schedule) uses stated methods with historical calibration; estimates presented without uncertainty are planning defects.
4. Control through measurement: project assessment uses defined measures (progress against plan, risk exposure, defect discovery) with thresholds that trigger replanning rather than silent hope.
5. Manage change formally: requirement and scope changes flow through change control with impact assessment across schedule, cost, and technical risk; ad-hoc absorption of scope is the project control failure.
6. Run milestone reviews as gates with entry/exit criteria: reviews verify readiness against criteria rather than presenting status; failed criteria defer the milestone, they do not generate action items that vanish.
7. Close with records: project closure captures actuals against estimates, process performance data feeding future calibration, and lessons integrated into organizational assets.

## Controls and evidence

- Tailoring record per project with rationale.
- Estimation method and calibration records with uncertainty statements.
- Project measurement definitions and threshold-triggered replanning records.
- Change control records with cross-dimensional impact assessments.
- Milestone review records with criteria outcomes.
- Closure records with actuals and calibration data.

## Validation

- Sample one project: confirm tailoring decisions exist and match the project's lifecycle reality.
- Confirm at least one measurement threshold triggered a recorded replanning in the sample period.
- Confirm closure records fed estimation calibration data into organizational assets.

## Failure correction

- **Scope absorbed without change control** → retroactive impact assessment, decision to absorb or reverse at authority level, and closure of the intake path that bypassed control.
- **Estimates without stated method** → recalibrate using historical actuals and record the method before the next planning cycle.
- **Milestone review with waived criteria** → record the waiver decision and authority; silent waivers invalidate the review gate.

## Limitations

16326 governs the process frame; methodology (agile, plan-driven, hybrid) is a tailoring choice within it. The standard presumes an engineering organization with baseline process maturity; highly improvised environments gain from adopting its control concepts first and its full process model later.

## Scope note

This article is part of the engineering leaf. Cross-reference: `IEEE_12207_2017_LIFECYCLE_TAILORING_GOVERNANCE.md`, `IEEE_29148_2018_REQUIREMENTS_ENGINEERING_GOVERNANCE.md`, and `ISO_IEC_15939_2017_MEASUREMENT_PROCESS_GOVERNANCE.md`.

## Canonical sources

- IEEE 16326-2023 — Standard for Application of Project Management Processes for Systems and Software Engineering: https://standards.ieee.org/ieee/16326/
- ISO/IEC/IEEE 12207:2017 — Systems and software engineering — Software life cycle processes: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:12207:ed-2
- ISO/IEC/IEEE 15288 — System life cycle processes: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:15288
- ISO 21500 — Project, programme and portfolio management — Context and concepts: https://www.iso.org/obp/ui/#iso:std:iso:21500
- PMI — Project Management Body of Knowledge (PMBOK Guide): https://www.pmi.org/
