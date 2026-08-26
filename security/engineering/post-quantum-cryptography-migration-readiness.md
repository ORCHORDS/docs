# post-quantum-cryptography-migration-readiness

**Issue:** Systems depend on public-key cryptography with no inventory or migration plan for post-quantum algorithms.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A team knows that post-quantum migration is relevant but cannot identify where key exchange, certificates, signatures, firmware validation, API integrations, or long-retained encrypted data depend on classical public-key algorithms.

## Root cause

Cryptographic agility is an architecture property, not a last-minute library upgrade. NIST standardized ML-KEM in FIPS 203 for key encapsulation; migration requires knowing where public-key cryptography is used, how protocol peers negotiate algorithms, and which vendors can support interoperable upgrades.

**Source:** [NIST FIPS 203 — ML-KEM](https://csrc.nist.gov/pubs/fips/203/final).

## Fix

Build a risk-based migration program:

- inventory cryptographic uses by protocol, algorithm, library, certificate, key owner, data lifetime, and external dependency;
- prioritize long-lived confidential data and systems with long replacement cycles;
- require crypto-agile interfaces that can negotiate and rotate algorithms without changing application semantics;
- test hybrid or phased interoperability only with supported protocol/library/vendor combinations;
- define key lifecycle, certificate, logging, rollback, and incident procedures before production rollout;
- track vendor roadmaps and published errata rather than pinning a migration plan to a single early implementation.

## Verification

- The inventory identifies every production public-key use and a responsible owner.
- A representative integration completes the agreed migration or interoperability test with documented algorithm negotiation.
- A failed rollout can return to an approved classical configuration without data loss or insecure downgrade.
- Security review confirms that algorithm changes did not weaken authentication, key validation, or downgrade resistance.

## Gotchas

- Post-quantum readiness does not mean inventing a custom cryptosystem or replacing symmetric cryptography indiscriminately.
- Algorithm names alone are insufficient; protocol negotiation, certificate ecosystems, hardware support, and peer compatibility decide viability.
- Avoid “harvest now, decrypt later” claims without first classifying data retention and threat model.

## Related

- the key rotation guidance in this file
- the mTLS sections in this file
- `infra/secrets-management.md`
