# NIST SP 800-218A AI model secure-development profile

**Issue:** Conventional application SDLC controls omit model-specific supply-chain and lifecycle risks such as opaque training inputs, untrusted weights, unsafe model serialization, and model behavior changes after updates.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Use final NIST SP 800-218A as an AI-specific community profile alongside—not instead of—final SSDF 1.1. It applies to model producers, systems that use models, and acquirers.

## Controls

- Define roles across data, model, application, evaluation, deployment, and incident response.
- Inventory training/evaluation datasets, model weights, adapters, tokenizers, code, and external services with source, license, integrity, and owner.
- Isolate acquisition and conversion of untrusted model artifacts; avoid unsafe deserialization formats and execution paths.
- Protect model and dataset pipelines from unauthorized change and preserve build/training provenance.
- Define security tests for misuse, prompt-mediated attacks, model extraction, sensitive-data disclosure, and unsafe tool invocation relevant to the system.
- Approve changes to models, prompts, retrieval corpora, tools, guardrails, and inference infrastructure as release inputs.
- Monitor behavior and vulnerabilities after deployment; retain a rollback-capable known-good model bundle.
- Communicate security-relevant limitations to integrators without exposing exploitable details.

## Verification

1. Reconstruct a released model bundle from approved inputs or explain non-reproducible stages.
2. Verify every weight and auxiliary artifact by digest.
3. Exercise malicious model/package fixtures in isolation.
4. Rerun security evaluations after any behavior-affecting component changes.
5. Trace a sampled SP 800-218A task to implementation, evidence, owner, and exception.
6. Run rollback and incident-notification exercises.

## Gotchas

SP 800-218A augments SSDF; implementing only AI additions leaves ordinary software controls uncovered. Model cards are communication artifacts, not provenance or security evidence. A model digest does not establish trustworthy training data or behavior.

## Sources

- [NIST SP 800-218A final publication](https://csrc.nist.gov/pubs/sp/800/218/a/final)
- [NIST SSDF publications](https://csrc.nist.gov/Projects/ssdf/publications)
- [NIST SP 800-218 final](https://csrc.nist.gov/pubs/sp/800/218/final)
