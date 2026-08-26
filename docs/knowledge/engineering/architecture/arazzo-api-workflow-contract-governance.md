# Arazzo API workflow contract governance

**Issue:** An OpenAPI document describes individual HTTP operations, but a real integration usually needs an ordered flow—create, authorize, confirm, poll, then retrieve—with inputs, dependencies, and failure branches. Leaving that flow only in prose produces client implementations that disagree on sequencing and error handling.

**Date:** 2026-08-17
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Use the right contract layer

The Arazzo Specification defines workflows: sequences of calls and dependencies that deliver an outcome in the context of API descriptions such as OpenAPI. It complements an operation-level OpenAPI contract; it does not replace service authorization, orchestration code, or end-to-end testing.

1. **Define a user-visible outcome.** Each workflow should name the outcome it delivers, such as account onboarding or payment confirmation, rather than mirror every endpoint.
2. **Reference stable source descriptions.** Bind workflow steps to versioned OpenAPI descriptions. Validate that each referenced operation still exists and accepts the mapped input.
3. **Make data flow explicit.** Record where every step’s parameter comes from and where its output is used. Avoid implicit state stored only in an SDK.
4. **Specify expected failure paths.** Document retryable versus terminal errors, compensation or cleanup operations, polling limits, and idempotency requirements for the workflow—not merely the happy path.
5. **Test generated and hand-written clients against the workflow.** A workflow that parses is not proven correct until its sequences and failure paths run against a compatible environment.

## Governance

1. Version workflows with their source contracts and publish the compatibility relationship.
2. Require review from the service owner for changes that add a side effect, broaden data sharing, or alter compensation.
3. Run a CI check that resolves references, validates documents, and executes representative workflow tests.
4. Treat workflow diagrams and generated examples as derived output; the reviewed source is the Arazzo/OpenAPI pair.
5. Do not encode credentials, live user data, or privileged headers in workflow examples.

## Sources

- [Arazzo Specification v1.1.0](https://spec.openapis.org/arazzo/latest.html)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
