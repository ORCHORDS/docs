# NIST ARIA Measurement Trees and Three-Level AI Evaluation

**Issue:** Model benchmarks alone do not establish whether an AI application remains valid and safe when people use it in realistic contexts.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Define a measurement tree that links deployment claims to constructs, observable indicators, metrics, and decision thresholds.
- Evaluate at three levels: model testing, adversarial red teaming, and field testing with representative human interaction.
- Use application scenarios that preserve task, population, environment, and consequence context rather than generic prompts alone.
- Collect quantitative results and structured tester or annotator judgments with documented sampling and uncertainty.
- Keep release decisions separate from the evaluators who design or score the evidence where practical.

## Verification

- Trace every launch claim to at least one observable measure and explicit threshold.
- Compare model-only results with red-team and field results and investigate reversals.
- Repeat a stable scenario after model, prompt, tool, policy, or user-population changes.

## Gotchas

- Verify source maturity and product support before making a normative claim.
- Keep secrets, tokens, personal data, and restricted evidence out of examples and logs.
- Reassess after material changes to scope, dependencies, or enforcement.

## Sources

- https://www.nist.gov/publications/assessing-risks-and-impacts-ai-aria-pilot-evaluation-report
- https://doi.org/10.6028/NIST.AI.700-2
