# ISO/IEC 14143 Functional Size Measurement Governance

## Purpose

ISO/IEC 14143 (multiple parts), *Information technology — Software and systems engineering — Software measurement — Functional size measurement (FSM)*, defines the general framework and conformance requirements for functional size measurement methods — measuring software size by its functional content (what it does for users) rather than code volume or effort.

Organizations using functional size measures for estimation, benchmarking, or contractual sizing should ground their method choice in 14143's framework so that size measures are defensible, repeatable, and comparable.

## Scope

Applies to the studio's software sizing practice for estimation and benchmarking. Covers FSM method selection, conformance, and measurement application discipline. Does not cover specific FSM methods beyond their framework relationship (COSMIC ISO/IEC 19761, IFPUG ISO/IEC 20926, and others are certified against the framework).

## Workflow

1. Select an FSM method certified against 14143 conformance (COSMIC per ISO/IEC 19761 and IFPUG function points per ISO/IEC 20926 are the prominent candidates); record the selection and rationale per domain.
2. Apply 14143-1's measurement framework concepts: the functional user, the boundary of the measurement, and the functional processes — sizing disciplines live or die on boundary definition.
3. Establish a measurement procedure per method: trained measurers, documented counting rules for the domain, and resolution paths for ambiguous cases.
4. Calibrate estimation against measured size: size measures feed effort estimation only through calibration with the organization's historical size-to-effort data; uncalibrated ratios are folklore.
5. Maintain comparability: sizes measured under different methods or counting conventions do not mix; the repository records method and convention per measurement.
6. Re-measure on scope change: functional size changes when functional content changes; estimates re-baselined against re-measured size, not adjusted by intuition.
7. Audit measurement consistency: independent re-counts on samples verify measurer consistency within tolerance; beyond-tolerance divergence triggers counting-rule clarification.

## Controls and evidence

- FSM method selection record with rationale and domain scope.
- Domain counting rules documentation with ambiguity resolutions.
- Size-to-effort calibration dataset with historical measurements.
- Measurement repository with method and convention metadata.
- Re-measurement records on scope changes.
- Consistency audit results (independent re-counts with tolerance).

## Validation

- Sample three measurements and confirm each records method, boundary, and counting convention.
- Confirm the estimation model in use is calibrated against the historical dataset, with the calibration date recorded.
- Confirm the last consistency audit ran within cadence with divergences resolved.

## Failure correction

- **Sizes from different conventions mixed in one analysis** → segregate by convention and re-baseline; mixed-convention comparisons are invalid.
- **Estimation ratios uncalibrated** → build or refresh the calibration dataset before the next estimate relies on it.
- **Measurer divergence beyond tolerance** → clarify the counting rule, retrain, and re-audit.

## Limitations

FSM measures functional size, not complexity, technical difficulty, or non-functional effort — estimation models need adjustment factors with their own calibration. Methods differ in applicability (COSMIC targets real-time and business software; IFPUG function points are business-application centric); method selection constrains domain coverage. FSM's value compounds with history: early measurements feed weak calibration until the dataset matures.

## Scope note

This article is part of the engineering leaf. Cross-reference: `ISO_IEC_15939_2017_MEASUREMENT_PROCESS_GOVERNANCE.md`, `IEEE_16326_2023_PROJECT_MANAGEMENT_GOVERNANCE.md`, and `ISO_IEC_25012_2008_DATA_QUALITY_MODEL_GOVERNANCE.md`.

## Canonical sources

- ISO/IEC 14143-1 — Software measurement — Functional size measurement — Definition of concepts: https://www.iso.org/obp/ui/#iso:std:iso-iec:14143:-1
- ISO/IEC 19761 — COSMIC method (FSM method certified against the framework): https://www.iso.org/obp/ui/#iso:std:iso-iec:19761
- ISO/IEC 20926 — IFPUG function point analysis method: https://www.iso.org/obp/ui/#iso:std:iso-iec:20926
- ISO/IEC/IEEE 12207:2017 — Software life cycle processes (estimation context): https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:12207:ed-2
- COSMIC — COSMIC measurement manual: https://cosmic-sizing.org/
