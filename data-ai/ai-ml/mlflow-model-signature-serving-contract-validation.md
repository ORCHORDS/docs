# MLflow Model Signature Serving Contract Validation

**Issue:** A model can load successfully while production requests have missing columns, unsafe coercions, or wrong tensor shapes. An explicit MLflow signature makes the serving boundary testable.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Log a representative input example and an explicit or inferred input, output, and parameter signature.
- Treat signature changes as API changes: compare them during promotion and require compatibility approval.
- Validate through the PyFunc or deployment interface used in production; native flavor loading may not enforce the signature.
- Keep optional fields explicit and include null or missing-value cases in examples.

## Verification

- Run mlflow.models.predict with the stored serving example in an isolated environment.
- Negative-test missing required fields, extra fields, unsafe types, tensor shapes, and unknown parameters.
- Reload the promoted artifact and assert its recorded signature, not only the training object.

## Gotchas

- MLflow validates inputs but type-hint output annotations are not runtime output validation.
- Safe type conversions may occur; test the exact coercions your risk model permits.

## Official sources

- https://mlflow.org/docs/latest/ml/model/signatures
