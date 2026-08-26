# OpenTofu state and plan encryption rollover

**Issue:** Enabling encryption with one new key can make existing state, saved plans, and remote-state consumers unreadable if the migration is not staged and recoverable.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Pin the OpenTofu version and configure encryption separately for state, plan, and `terraform_remote_state` use. Prefer an approved KMS-backed key provider over a static passphrase, and protect both provider credentials and configuration. During initial enablement or rotation, retain an explicit fallback method that can decrypt the old material while the primary method writes with the new key; remove the fallback only after every relevant artifact has been rewritten and restored in a test.

Back up state and key-recovery material through separate governed channels. Encryption protects stored contents from disclosure; it does not prevent state loss, replay of an older state or plan, or disclosure to the operator running `tofu`. Preserve backend locking, versioning, and exact plan-to-apply revision checks.

## Verification

Clone a sanitized production-shaped state, enable encryption, run plan/apply without infrastructure changes, rotate the key, and restore with the documented break-glass path. Test old/new clients, remote-state readers, saved plans, backend history, unavailable KMS, wrong key, rollback, and fallback removal.

## Gotchas

- Removing the last working decryption method can make state unrecoverable.
- AES-GCM key usage and provider rotation policy must be governed.
- Encryption metadata and keys need compatible migration ordering.

## Official source

- [OpenTofu state and plan encryption](https://opentofu.org/docs/v1.10/language/state/encryption/)
