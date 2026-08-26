# Terraform ephemeral-resource state exclusion

**Issue:** Short-lived credentials or connections become durable secrets when modeled as ordinary Terraform resources or data sources, but assuming ephemeral means leak-proof ignores provider, log, and downstream behavior.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Require Terraform 1.10 or later and provider-declared support before using an `ephemeral` block.
- Keep ephemeral values only in allowed ephemeral contexts such as other ephemeral blocks, ephemeral variables or outputs, provider configuration, provisioners, and supported write-only arguments.
- Design for the open, renew, and close lifecycle. Set remote lease TTLs and revocation behavior so interruption, retry, and a delayed apply remain safe.
- Inspect provider and CI logs, crash reports, command output, and remote APIs; omission from plan and state does not stop another component from persisting the value.
- Separate plan-only credentials from apply privileges and rotate any lease whose close step cannot be proven after failure.

## Verification

Generate a plan, saved plan, state, JSON output, debug log, and failed run and scan each for a canary secret. Test deferred apply-time creation, renewal, cancellation, provider crash, runner termination, and close/revocation. Confirm a non-ephemeral consumer is rejected.

## Gotchas

- `sensitive` redacts display; `ephemeral` controls persistence. They solve different problems.
- An ephemeral resource may still create externally durable effects.
- Provider support and minimum Terraform versions must be pinned across every runner.

## Official source

- [Terraform ephemeral block reference](https://developer.hashicorp.com/terraform/language/block/ephemeral)
- [Terraform ephemeral values in resources](https://developer.hashicorp.com/terraform/language/manage-sensitive-data/ephemeral)
