# Validate Certificate Transparency v2 Log Proofs

**Issue:** RFC 9162 Certificate Transparency evidence depends on log identity, signature scheme, tree size, timestamps, Merkle inclusion or consistency proofs, and a policy-selected set of trusted logs.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Pin trusted log IDs, public keys, operators, states, and accepted signature algorithms through a versioned policy.
- Validate Signed Certificate Timestamps and Signed Tree Heads against the correct log and serialized v2 structures.
- Verify inclusion proofs for the stated leaf and tree size; verify consistency before advancing a cached tree head.
- Enforce maximum merge delay, clock-skew, certificate lifetime, and log-diversity policy separately.
- Persist observed tree heads and escalate split-view or invalid-consistency evidence.

## Verification

- Run RFC test vectors and mutate leaf index, audit path, tree size, timestamp, signature, and log ID.
- Attempt rollback, inconsistent tree heads, and a valid proof from an untrusted or retired log.
- Cross-check tree heads through independent monitors.

## Gotchas

A valid SCT is a promise of logging, not proof of present inclusion until the relevant conditions and proof are verified. CT detects certificate issuance; it does not replace PKIX service-identity validation.

## Official sources

- [RFC 9162](https://www.rfc-editor.org/rfc/rfc9162.html)
