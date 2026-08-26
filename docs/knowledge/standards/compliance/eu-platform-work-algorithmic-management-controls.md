# EU Platform Work Algorithmic-Management Controls

**Issue:** Directive (EU) 2024/2831 creates specific duties for digital labour platforms using automated monitoring or decision systems, including prohibited processing, transparency, human oversight, review, and worker consultation.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Inventory automated systems that monitor, evaluate, allocate work, set pay, restrict accounts, or support consequential decisions.
- Block the prohibited data uses in Article 7, including collection while a person is not offering or performing platform work and inference of protected characteristics.
- Maintain worker-facing notices describing monitored data, system purpose, decision categories, main parameters, and grounds for decisions.
- Route significant adverse decisions to qualified human oversight and provide a reachable human contact, reasons, and a review/correction path.
- Retain system-change, risk-assessment, consultation, explanation, and human-review evidence by jurisdiction and transposition date.
- Prohibit dismissal or equivalent termination based solely on an automated decision.

## Verification

- Trace sampled decisions from inputs and model/version through notice, explanation, human review, and final outcome.
- Test that prohibited attributes and off-duty collection cannot enter monitoring pipelines.
- Conduct access and correction exercises with worker representatives and measure response deadlines.
- Review national transposition before launch because the Directive requires Member State implementation.

## Gotchas

This is not satisfied by a generic privacy notice or a model card. The Directive applies controls to automated monitoring as well as automated decisions, and its employment-status rules are separate from the algorithmic-management duties.

## Official sources

- [Directive (EU) 2024/2831](https://eur-lex.europa.eu/eli/dir/2024/2831/oj/eng)
