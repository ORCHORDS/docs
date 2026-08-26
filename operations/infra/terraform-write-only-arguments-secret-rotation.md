# Terraform write-only arguments and secret rotation

**Issue:** Removing a password or API key from Terraform state can also remove the diff signal that tells Terraform when the remote secret must be changed.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Require Terraform 1.11 or later and verify the exact provider resource marks the argument write-only; naming a field with `_wo` does not create the behavior.
- Feed write-only arguments from ephemeral values where possible. Confirm the value is absent from plan and state, while still protecting configuration, logs, provider requests, and the destination.
- Use the provider's companion version field, commonly an `_wo_version` argument, as the durable rotation signal. Advance it in the same reviewed change as secret rotation.
- Make retries idempotent and keep the previous credential valid until the remote update and dependent rollout are verified.
- Document recovery when apply succeeds remotely but state or the runner fails before recording the version.

## Verification

Scan plan, saved plan, state, JSON, logs, and failure artifacts with a canary value. Apply the same version twice, advance the version, interrupt during the remote update, roll back dependents, and prove the old credential is retired only after successful verification.

## Gotchas

- A write-only argument cannot produce a plan difference by its secret value alone.
- Not every provider or resource supports write-only arguments.
- State omission reduces one exposure path; it does not encrypt transport or the remote service.

## Official source

- [Terraform write-only arguments](https://developer.hashicorp.com/terraform/language/manage-sensitive-data/write-only)
- [Terraform provider framework write-only arguments](https://developer.hashicorp.com/terraform/plugin/framework/resources/write-only-arguments)
