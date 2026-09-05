# Cryptographic Agility Playbook

## Purpose

Enable a system to swap cryptographic algorithms, key lengths, and primitives without re-architecting applications, protocols, or data formats. Agility is the prerequisite for safe migration to post-quantum cryptography and for rapid response to algorithm compromise.

## Procedure

1. Inventory every algorithm, key length, mode, and parameter in use across protocols, libraries, configuration files, certificates, and data formats.
2. Abstract cryptographic operations behind stable interfaces (sign, verify, encrypt, decrypt, key-agree, key-derive) so that swapping the primitive does not require application changes.
3. Negotiate algorithm selection through protocol-level identifiers (TLS cipher suites, JOSE alg, COSE alg, PKIX signature algorithms) rather than hard-coded constants.
4. Carry the algorithm identifier alongside the artefact (signature, JWE, certificate, OID) so that data remains verifiable across transitions.
5. Maintain a parallel-runnable period where old and new algorithms coexist, with documented cutover dates and rollback paths.
6. Track cryptographic dependency surface in a software bill of materials (SPDX, CycloneDX) with algorithm and version metadata.
7. Review the inventory at the cadence defined in your cryptographic policy (quarterly minimum) and on every external trigger (NIST SP 800-131A Rev. 2 update, CNSA 2.0 update, algorithm deprecation).
8. Exercise the swap path in test environments annually to prove the abstraction does not regress.

## Source basis

- NIST SP 800-131A Rev. 2 (March 2024).
- NIST FIPS 140-3, FIPS 180-5, FIPS 186-5, FIPS 197, FIPS 202, FIPS 203, FIPS 204, FIPS 205.
- NSA CNSA 2.0.
- IETF RFC 7696 (Guidelines for Cryptographic Algorithm Agility).
