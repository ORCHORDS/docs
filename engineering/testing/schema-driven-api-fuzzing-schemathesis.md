# schema-driven-api-fuzzing-schemathesis

**Issue:** API tests cover hand-picked examples but miss invalid combinations and stateful edge cases permitted by the implementation but absent from the contract.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

An OpenAPI or GraphQL schema can generate broad positive and negative test cases. Schema-driven fuzzing finds discrepancies between declared contract and runtime behavior, but destructive or stateful cases need isolated data, authentication boundaries, and minimal reproducible failure artifacts.

**Source:** [Schemathesis documentation](https://schemathesis.readthedocs.io/en/stable/).

## Fix

- make the API schema versioned, accurate, and available to CI;
- generate tests in isolated environments with scoped credentials and test data;
- classify safe read-only checks separately from destructive/stateful operations;
- retain the minimal reproducer, seed, request, response class, and schema revision for failures;
- add regressions for every discovered contract violation;
- gate promotion on agreed error, authorization, and response-schema invariants.

## Verification

- Generated invalid inputs cannot bypass authorization or crash the service.
- A discovered failure reproduces from the saved minimal case.
- Stateful tests clean up or run against disposable data.
- Schema changes and implementation changes are tested together.

## Related

- `testing/fuzz-testing-basics.md`
- `cloudflare/api-shield-schema-validation-2-rollout.md`
