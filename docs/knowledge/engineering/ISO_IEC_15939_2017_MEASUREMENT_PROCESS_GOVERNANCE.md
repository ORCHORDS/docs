# ISO/IEC/IEE 15939:2017 Measurement Process Governance

## Purpose

ISO/IEC/IEEE 15939:2017, *Systems and software engineering — Measurement process*, defines the measurement process for systems and software: establishing measurement constructs (base and derived measures, indicators), collecting and analyzing data, and evaluating the measurement information products against information needs.

Organizations measuring engineering processes should apply 15939's model so that metrics are designed constructs answering stated information needs, not arbitrary numbers collected because tools make them available.

## Scope

Applies to the studio's software and systems measurement practice. Covers the measurement process, measurement constructs, and information product evaluation. Does not cover specific metrics catalogues or analytics tooling.

## Workflow

1. Start from information needs: state the decision each measurement supports before selecting measures; a measure without a stated information need is data collection, not measurement.
2. Define measurement constructs per the model: base measures (directly counted or observed), derived measures (functions of base measures), and indicators (measures plus decision criteria) — with each construct's characteristics (unit, method, scale) documented.
3. Apply the measurement process phases: establish and sustain measurement commitment, plan measurement, perform measurement (collect, verify, analyze), and evaluate the measurement products.
4. Verify collected data: validation rules at collection catch the defects that silently corrupt indicators; unverified data feeds decisions with unknown error.
5. Analyze against the information need: indicators are interpreted against their decision criteria, producing information products that answer the question the measurement exists for.
6. Evaluate the measurement itself: periodically assess whether the constructs still serve their information needs; measures that answer dead questions are retired.
7. Record measurement metadata: for each measure, the collection point, method, owner, and known limitations — limitations recorded, not discovered during a bad decision.

## Controls and evidence

- Information needs register with decisions and owners.
- Measurement construct definitions (base, derived, indicators) with characteristics.
- Data verification rules and their execution records.
- Information products delivered to decision owners on cadence.
- Measurement evaluation records with retirements and revisions.

## Validation

- Sample three indicators and confirm each traces to a live information need with a decision owner.
- Confirm data verification rules run at collection for the sampled measures.
- Confirm the last measurement evaluation retired or revised dead measures.

## Failure correction

- **Measure without an information need** → attach one or retire the measure; orphan collection is cost without decision value.
- **Verification gap corrupting indicators** → add validation rules, quantify the historical corruption, and re-baseline affected indicators.
- **Indicator no longer driving decisions** → retire it and record the retirement in the evaluation.

## Limitations

15939 governs the measurement process, not metric selection — what to measure depends on context (cost, schedule, quality, performance). The model's discipline shows its value over years; single-metric instantiations gain little from the full process overhead.

## Scope note

This article is part of the engineering leaf. Cross-reference: `ISO_IEC_25010_2011_SOFTWARE_PRODUCT_QUALITY_MODEL.md`, `IEEE_730_2014_SOFTWARE_QUALITY_ASSURANCE_PLAN_GOVERNANCE.md` (standards leaf), and `SRE_RELEASE_COORDINATION_ERROR_BUDGET_GOVERNANCE.md` (operations leaf).

## Canonical sources

- ISO/IEC/IEEE 15939:2017 — Systems and software engineering — Measurement process: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:15939:ed-2
- ISO/IEC 25020 — Systems and software engineering — SQuaRE — Measurement reference model and guide: https://www.iso.org/obp/ui/#iso:std:iso-iec:25020
- ISO/IEC/IEEE 12207:2017 — Software life cycle processes: https://www.iso.org/obp/ui/#iso:std:iso-iec-ieee:12207:ed-2
- ISO 9001:2015 — Quality management systems — Requirements: https://www.iso.org/obp/ui/#iso:std:iso:9001:ed-5
- Practical Software and Systems Measurement (PSM) — measurement guidance aligned to 15939: https://www.psmsc.com/
