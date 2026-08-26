# machine-unlearning-governance

**Issue:** A team promises to “delete” a subject’s influence from an ML model without defining the method, evidence, limitations, or retraining fallback.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

Machine unlearning is not simply deleting a source row. It concerns reducing or removing the effect of particular training data from a trained model, and methods may be approximate. Claims must distinguish data deletion, model retraining, approximate unlearning, and verification evidence.

**Source:** [NIST machine-unlearning glossary](https://csrc.nist.gov/glossary/term/machine_unlearning).

## Fix

- document the request scope, affected datasets, model versions, and legal basis;
- classify whether full retraining, approved approximate unlearning, or another control is required;
- retain evidence of method, input lineage, affected artifacts, evaluation, and residual limitations;
- prohibit unsupported marketing or compliance claims about exact erasure;
- define rollback and redeployment controls for affected models.

## Verification

- A request maps to exact data and model versions.
- The selected method and its limitations are reviewable.
- Post-change evaluation is recorded against a defined baseline.
- Unsupported requests escalate rather than receive a false assurance.

## Related

- `ai-ml/ml-experiment-reproducibility-evidence.md`
- `compliance/gdpr-data-subject-rights-api.md`
