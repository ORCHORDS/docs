# IEEE 1044 Software Anomaly Classification Governance

## Purpose

IEEE 1044, *Standard Classification for Software Anomalies*, provides a uniform scheme for classifying software anomalies: what failed, how it failed, what effect it had, and how the failure was found. A consistent classification scheme makes defect data comparable across projects, enabling defect analysis, prevention, and process feedback instead of anecdote-driven quality work.

Teams should apply the standard's classification attributes so that every anomaly record carries the structured attributes (failure cause, failure mode, effect, detection method) that analysis and prevention actually consume.

## Scope

Applies to the studio's anomaly (defect, bug, fault report) recording practice. Covers classification attributes, recording discipline, and analysis use. Does not cover triage prioritization mechanics or incident response.

## Workflow

1. Adopt the standard's attribute structure in the defect tracking schema: anomaly description, origin (lifecycle phase introduced), cause category, failure mode, effect (severity to users and operations), and detection phase and method.
2. Classify at recording time by the person with the facts: the reporter classifies observed behavior (effect, detection context); developers classify cause after analysis — classification is a two-stage discipline, not a one-shot guess.
3. Train classifiers on the cause categories: misclassification (everything is "logic error") collapses the analytical value; the scheme's categories work only when applied with shared understanding.
4. Record detection phase accurately: where the anomaly was found (which test level, review, field) feeds escape analysis — the comparison of detection phase against origin phase that identifies process gaps.
5. Analyze on cadence: defect distribution by cause category, origin phase, and detection phase; escape analysis (defects found downstream of their origin) identifies where verification effort is misallocated.
6. Feed prevention: recurring cause categories trigger prevention actions (design reviews, checklists, tooling) targeted at the categories actually recurring, measured by subsequent reduction.
7. Audit classification quality periodically: sampled re-classification against the definitions measures classification consistency; drift degrades every downstream analysis.

## Controls and evidence

- Defect schema implementing the classification attributes.
- Two-stage classification records (reporter + developer) per anomaly.
- Detection and origin phase records enabling escape analysis.
- Cadenced defect analysis reports (distribution and escapes).
- Prevention action records tied to cause categories.
- Classification audit results with consistency measures.

## Validation

- Sample 20 anomaly records and confirm the classification attributes are populated with distinct values (not collapsed categories).
- Confirm escape analysis ran on cadence and produced verification-allocation findings.
- Confirm at least one prevention action traces to a recurring cause category with measured reduction.

## Failure correction

- **Category collapse (one cause dominates unrealistically)** → clarify category definitions, retrain, and re-audit until distribution is plausible.
- **Detection phase unrecorded** → make it mandatory at resolution; escape analysis is impossible without it.
- **Analysis without prevention action** → treat recurring categories without actions as a process decision (accepted) or a gap (act), recorded either way.

## Limitations

Classification consumes effort at recording time; over-ambitious schemas are abandoned by teams under pressure — implement the standard's core attributes, extend only where analysis consumes the data. Causal classification for complex failures is judgment work; audits keep it honest but cannot make it mechanical.

## Scope note

This article is part of the engineering leaf. Cross-reference: `IEEE_1028_2008_REVIEW_TYPES_SELECTION_GOVERNANCE.md`, `ISO_IEC_IEEE_29119_1_2022_TESTING_CONCEPTS_GOVERNANCE.md`, and `ISO_IEC_15939_2017_MEASUREMENT_PROCESS_GOVERNANCE.md`.

## Canonical sources

- IEEE 1044 — Standard Classification for Software Anomalies (IEEE Standards Association): https://standards.ieee.org/standard/1044.html
- IEEE 1028-2008 — Standard for Software Reviews and Audits (IEEE Standards Association): https://standards.ieee.org/ieee/1028/3438/
- ISO/IEC/IEEE 12207:2017 — Software life cycle processes: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:12207:ed-2
- ISO/IEC/IEEE 29119-2 — Test processes: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:29119:-2
- ISO/IEC/IEEE 15939:2017 — Measurement process: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:15939:ed-2
