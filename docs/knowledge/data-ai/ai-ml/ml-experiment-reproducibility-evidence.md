# ml-experiment-reproducibility-evidence

**Issue:** A model is promoted without enough evidence to reproduce the training or evaluation result.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

A model artifact alone cannot explain how it was produced or whether a later result is comparable. Reproducibility requires linked evidence for source, data version, environment, configuration, seed, evaluation protocol, metrics, and the resulting artifact.

**Source:** [MLflow Tracking documentation](https://mlflow.org/docs/latest/ml/tracking/).

## Fix

- assign an immutable run ID to every promotion candidate;
- record source revision, dependency/environment digest, data lineage/version, configuration, random seed, and hardware/runtime details;
- preserve evaluation dataset identity, metric definitions, thresholds, and produced artifacts;
- compare promotions only against compatible evaluation protocols;
- require a reviewable run record before deployment;
- retain enough evidence to reproduce or explain a decision without retaining disallowed raw data.

## Verification

- A reviewer can recreate the environment and locate the exact data/version and configuration.
- Re-running an unchanged experiment produces results within defined tolerance.
- A missing seed, dataset version, or metric definition blocks promotion.
- Evaluation evidence links to the deployed artifact.

## Related

- `ai-ml/model-versioning-strategy.md`
- `ai-ml/prompt-testing-evals.md`
