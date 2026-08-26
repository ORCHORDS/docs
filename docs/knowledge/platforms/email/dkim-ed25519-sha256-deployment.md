# DKIM Ed25519-SHA256 deployment

**Issue:** RSA-only DKIM estates can be operationally heavy, while an incorrect Ed25519 rollout can publish malformed keys or break receivers that do not support the algorithm.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Treat `ed25519-sha256` as an additional DKIM signing path during migration. Keep a proven RSA signature until receiver coverage and telemetry justify any retirement.
- Publish the Ed25519 public key in a selector-specific DKIM TXT record with `k=ed25519`; store the private key only in the signing service or managed secret boundary.
- Use distinct selectors for RSA and Ed25519 so rotation, rollback, and incident isolation do not couple the algorithms.
- Canonicalize and hash exactly as DKIM specifies; algorithm choice does not excuse header selection, body-length, or replay-risk mistakes.
- Inventory verifier support and monitor results by algorithm, receiver, selector, and failure class.

## Verification

1. Generate a test message signed with both algorithms and validate it using independent DKIM implementations.
2. Resolve the selector through authoritative and recursive DNS and verify the decoded key is exactly 32 octets.
3. Alter a signed header and body byte to prove both signatures fail when their signed material changes.
4. Exercise selector rotation with overlapping DNS TTLs and delayed mail.
5. Analyze aggregate authentication telemetry and sampled headers for unsupported-algorithm versus cryptographic failures.

## Gotchas

RFC 8463 encodes an Ed25519 public key in base64 in the DKIM key record; it does not use a PEM wrapper. Some older receivers ignore an unknown algorithm, which is why dual-signing is safer than an abrupt replacement. A second signature adds header size and DNS lookups, so measure deliverability rather than assuming stronger cryptography alone improves inbox placement.

## Sources

- [RFC 8463: A New Cryptographic Signature Method for DKIM](https://www.rfc-editor.org/rfc/rfc8463.html)
- [RFC 6376: DomainKeys Identified Mail](https://www.rfc-editor.org/rfc/rfc6376.html)
