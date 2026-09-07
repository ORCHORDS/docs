---
title: "HashiCorp Vault Transit Secret Engine Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "HashiCorp Vault Transit secret engine documentation and Vault release notes"
---

# HashiCorp Vault Transit Secret Engine Version Governance

## Overview

The Vault Transit secret engine performs cryptographic operations on demand without exposing plaintext data to client applications. This pattern decouples key custody from application processes, enabling centralized key management, auditable rotation, and reproducible encryption across distributed services and pipelines.

## Key Types

The Transit engine supports the following key types:

- `aes128-gcm96` and `aes256-gcm96` for symmetric authenticated encryption
- `chacha20-poly1305` for environments lacking AES-NI acceleration
- `rsa-2048` and `rsa-4096` for asymmetric wrapping and sign/verify operations
- `ecdsa-p256` for elliptic-curve signatures with compact key material
- `ed25519` for high-throughput deterministic signatures

## Operations

The engine exposes nine primary operations: `encrypt`, `decrypt`, `rewrap`, `rotate`, `datakey`, `hmac`, `sign`, `verify`, and `hash`. The `rewrap` primitive re-encrypts ciphertext against the latest key version without exposing plaintext, which is the recommended migration path during scheduled rotation.

## Versioning and Rotation

Each named key maintains an ordered version chain. The `rotation_period` parameter schedules automatic version advancement. `allow_plaintext_backup` governs export of the underlying key material, and `deletion_allowed` controls whether obsolete versions may be purged from the chain.

## Convergent Encryption

Convergent encryption derives ciphertext deterministically from plaintext through a caller-supplied `context` and a per-key `nonce`. Identical plaintext and context produce identical ciphertext, enabling deduplication while preserving semantic security when context is treated as non-secret.

## Key Derivation

`convergent_encryption` and `derived` keys allow downstream keys to be generated deterministically from a Transit-managed root, supporting hierarchical key architectures without persisting derived key material.

## Wrapping Tokens

The engine supports `wrap` and `unwrap` operations for exporting short-lived tokens via Cubbyhole-style response wrapping flows used in CI/CD handoff patterns.

## Auto-rotation and Minimum Decryption Version

`min_decryption_version` pins the oldest version still accepted for `decrypt` calls. Combined with `min_encryption_version`, it enforces a controlled cutover window during key rotation events and gradual retirement of legacy versions.

## HSM Integration

Enterprise deployments may back Transit keys with PKCS#11 or KMIP hardware modules, anchoring key material in certified hardware and isolating plaintext from the Vault server process boundary.

## FIPS 140-3

Vault Enterprise offers a FIPS 140-3 validated build. Transit operations executed within this build satisfy regulated environments requiring validated cryptographic modules.

## Compatibility Horizon

The reference target is Vault 1.18.x. Behavior is verified against upstream Transit documentation and release notes as of the review date.

## Decision Tree

- Choose `aes256-gcm96` for bulk data; reserve RSA or ECDSA for asymmetric flows.
- Set `rotation_period` between 30 and 90 days for general data; shorten for high-sensitivity material.
- Enable convergent encryption only when deduplication is required and context is non-secret.
- Prefer HSM-backed keys when regulatory scope demands hardware custody.

## Operational Impact

Rotation windows must be communicated to consuming services in advance. Re-wrap jobs should be scripted, idempotent, and resumable. Audit logs should be retained for the full retention window of the most recent key version.

## Cross-references

- Vault Transit API: `vault-transit-api.md:42`
- Rotation policy: `key-rotation-policy.md:15`
- HSM configuration: `hsm-pkcs11-setup.md:88`

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
