# confidential-computing-attestation-and-key-release

**Issue:** A workload uses a trusted execution environment (TEE) but releases sensitive keys or trusts workload claims without verifying attestation evidence and policy.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A team describes a confidential VM, enclave, or container as “secure in use,” yet cannot show which measurement was verified, who verified it, which configuration was accepted, or how secret release is denied when attestation fails.

## Root cause

A TEE protects only against a defined threat model. Attestation is the evidence a relying party evaluates before trusting that workload environment; key release must be bound to verified claims and an explicit policy. Neither mechanism replaces application authentication, authorization, input validation, or secure software supply chain practices.

**Source:** [Confidential Computing Consortium — attestation](https://confidentialcomputing.io/2023/04/06/why-is-attestation-required-for-confidential-computing/) and [Microsoft Learn — Azure Attestation overview](https://learn.microsoft.com/en-us/azure/attestation/overview).

## Fix

- document the threat model, trusted computing base, accepted TEE platforms, and residual risks;
- verify evidence signature, issuer, freshness, workload measurement, and security-version claims against a versioned policy;
- release decryption keys only after successful policy evaluation, with short-lived credentials and a deny-by-default failure path;
- record attestation decision metadata without logging keys, raw secrets, or sensitive workload inputs;
- define renewal, revocation, patch, and rollback behavior for measurement or platform changes;
- test policy changes in a non-production environment before permitting key release.

## Verification

- A valid workload measurement receives only its intended scoped key material.
- A changed measurement, expired evidence, wrong issuer, or failed policy evaluation receives no key.
- **Replay protection:** require a verifier-issued nonce and bind the released key to an ephemeral key or authenticated channel proven by the attested workload — signature/issuer/timestamp alone do NOT prevent replay or relay of captured evidence while it is fresh.
- Key-release and attestation failures are observable with non-sensitive reason codes.
- Rotating an approved measurement works through a reviewed rollout and preserves fail-closed behavior.

## Gotchas

- Attestation establishes properties of an environment, not the authorization of an end user or API caller.
- A TEE does not automatically prevent insecure outputs, malicious application logic, or unsafe prompts.
- Vendor-specific attestation formats and key-release services can create portability constraints; document them early.

## Related

- `security/secrets-rotation-runbook-2026.md` or the rotation section in this file
- `security/supply-chain-npm-security.md`
- `infra/webassembly-component-model-capability-boundaries.md`
