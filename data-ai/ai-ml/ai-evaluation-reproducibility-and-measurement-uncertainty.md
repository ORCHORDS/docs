# AI evaluation reproducibility and measurement uncertainty

**Issue:** A single benchmark score is reported without dataset version, sampling variation, inference configuration, or uncertainty, so teams cannot reproduce or compare the result.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Treat AI evaluation as a versioned measurement process. NIST's AI Resource Center and Metrology Center frame testing, evaluation, validation, and verification as context-dependent methods; inclusion of a method is not NIST endorsement.

## Evaluation record

Capture use case and decision, model/service/version/digest, prompt/template, tool/retrieval configuration, dataset provenance/version, population and sampling, exclusions, preprocessing, metric definition, random seeds, inference parameters, evaluator versions, hardware/service region, run time, and raw outputs under appropriate privacy controls.

## Controls

- Separate development, tuning, validation, and held-out evaluation sets.
- Detect benchmark contamination and repeated tuning on test results.
- Run sufficient repetitions and report dispersion/confidence intervals where meaningful.
- Predefine thresholds and failure handling before seeing final results.
- Analyze subgroup and scenario performance relevant to affected users.
- Record human-rater instructions, agreement, and adjudication.
- Re-run after any behavior-affecting model, prompt, retrieval, tool, or policy change.

## Verification

A second operator reruns from the record and compares within stated tolerance. Perturb seeds/order and test sensitivity. Recompute metrics from raw outputs. Challenge whether the metric predicts the operational outcome.

## Gotchas

Deterministic settings do not guarantee identical hosted-model results. Narrow confidence intervals do not cure biased samples. Public benchmark gains can reflect contamination. One aggregate hides severe slice failures.

## Sources

- [NIST AI Metrology Center](https://airc.nist.gov/metrology/)
- [NIST AI Resource Center](https://airc.nist.gov/)
- [NIST AI RMF 1.0](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10)
