# RFC 6979 Deterministic ECDSA Version Governance

## Purpose

RFC 6979, *Deterministic Usage of the Digital Signature Algorithm (DSA) and Elliptic Curve Digital Signature Algorithm (ECDSA)* (August 2013), specifies deterministic nonce generation for DSA/ECDSA: deriving the per-signature nonce k from the private key and message hash with HMAC-based generation, eliminating dependence on per-signature randomness.

Implementations signing with ECDSA should cite RFC 6979 explicitly where deterministic nonces are used, and prefer deterministic construction in new deployments because ECDSA nonce failure is catastrophic private-key recovery.

## Current context and source status

RFC 6979 was published August 2013 as an Informational RFC and is not obsoleted. NIST SP 800-208 approves deterministic ECDSA constructions within FIPS scope (permitted under FIPS 186-5), aligning the IETF and NIST positions. EdDSA (RFC 8032) is deterministic by construction. Side-channel considerations for deterministic nonces (fault attacks targeting the fixed k) are documented in the literature and partially in SP 800-208's implementation guidance.

## Governance pattern

1. Cite RFC 6979 and record the curve and hash in use; deterministic nonces apply per signature over the same input domain as randomized ECDSA.
2. Prefer deterministic ECDSA (RFC 6979 / SP 800-208) or EdDSA for new signature deployments; record the rationale where randomized ECDSA is retained (module validation scope, protocol constraints).
3. Use a conformant HMAC-based nonce generation; the RFC's bits2octets/bits2int conversions and the HMAC loop are exact — reimplementation drift produces non-conformant (though verifiable) signatures.
4. Guard deterministic nonces against fault attacks where the threat model includes physical attackers: nonce checks or signature verification before release per SP 800-208 implementation guidance.
5. For FIPS-bound deployments, confirm the module's ACVP validation covers the deterministic construction per FIPS 186-5/SP 800-208; RFC 6979 citation alone does not establish FIPS approval.
6. Verify public keys before use: deterministic nonce generation fixes nonce quality, not invalid-curve or invalid-public-key attacks — those remain protocol-layer checks.
7. Reproduce the RFC 6979 test vectors (Appendix A.2, P-256 among them) before production use.

## Validation and evidence

Evidence includes:

- construction citation (RFC 6979 and/or SP 800-208) with curve and hash;
- randomized-retention rationale where applicable;
- conformance evidence: RFC 6979 Appendix A.2 vectors reproduced;
- fault-attack countermeasures documented where in scope;
- module validation certificate covering the deterministic construction for FIPS-bound use.

## Failure correction

Common defects include:

- Reimplemented nonce generation with subtle conversion errors, producing signatures that verify but are non-conformant.
- Deterministic nonces adopted without the SP 800-208 implementation countermeasures in fault-exposed environments.
- RFC 6979 cited as if it conferred FIPS approval; FIPS approval flows through FIPS 186-5/SP 800-208 validation.

Corrective actions include adopting a vetted implementation, adding fault countermeasures per SP 800-208, and correcting validation-scope claims.

## Limitations

RFC 6979 covers DSA/ECDSA only; EdDSA's determinism is native (RFC 8032). Deterministic nonces do not address key generation quality, public-key validation, or protocol misuse (missing domain parameters, hash truncation errors). RFC 6979 is Informational; FIPS approval runs through NIST's specifications.

## Nonce failure economics

ECDSA's per-signature nonce is the single most fragile element in deployed cryptography: a repeated nonce across two signatures reveals the private key algebraically, and biased nonces fall to lattice attacks. Deterministic generation converts this from a per-signature operational risk into an implementation-quality property — one conformance decision instead of billions of RNG draws. That asymmetry is why deterministic ECDSA or EdDSA is the default posture for new deployments.

## Canonical sources

- RFC 6979, *Deterministic Usage of the Digital Signature Algorithm (DSA) and Elliptic Curve Digital Signature Algorithm (ECDSA)* (RFC Editor): https://www.rfc-editor.org/rfc/rfc6979
- NIST SP 800-208, *Recommendation for Deterministic ECDSA and EdDSA* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/208/final
- FIPS 186-5, *Digital Signature Standard* (NIST CSRC): https://csrc.nist.gov/pubs/fips/186-5/final
- RFC 8032, *Edwards-Curve Digital Signature Algorithms (EdDSA)* (RFC Editor): https://www.rfc-editor.org/rfc/rfc8032
- NIST SP 800-57 Part 1 Rev 5, *Key Management Guidance* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/57/part1/r5/final

Sources were verified on September 2, 2026.
