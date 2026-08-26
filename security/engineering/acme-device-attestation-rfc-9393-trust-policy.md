# Separate ACME Device Attestation Evidence from Issuance Policy

**Issue:** RFC 9393 lets an ACME client answer a device-attest-01 challenge with attestation evidence, but valid evidence does not by itself decide whether a device should receive a certificate.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Pin accepted attestation formats, trust anchors, device models, firmware/security state, nonce binding, and freshness.
- Bind evidence to the ACME challenge, account/order, requested identifiers, and intended certificate profile.
- Evaluate attestation in a policy engine with versioned decisions and audit evidence.
- Protect privacy by minimizing stable device identifiers and limiting retention/access.
- Define behavior when attestation verification services are unavailable.

## Verification
- Replay evidence across nonce, account, order, and identifier changes.
- Test untrusted chains, revoked models, stale firmware, malformed evidence, and policy-version changes.
- Trace an issued certificate to evidence and decision.

## Gotchas
Attestation authenticates claims about a device under a trust model; it is not proof of current application behavior or user authorization.

## Official sources
- [RFC 9393](https://www.rfc-editor.org/rfc/rfc9393.html)
