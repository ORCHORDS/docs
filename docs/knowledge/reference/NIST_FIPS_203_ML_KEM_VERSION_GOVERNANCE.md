# FIPS 203 ML-KEM Version Governance

## Purpose

FIPS 203, *Module-Lattice-Based Key-Encapsulation Mechanism Standard* (August 2024), specifies ML-KEM, the NIST-standardized post-quantum key-encapsulation mechanism derived from CRYSTALS-Kyber. ML-KEM is the primary mechanism for migrating key establishment to post-quantum security, deployed predominantly in hybrid constructions alongside classical ECDH during the transition.

Implementations adopting post-quantum key establishment should cite FIPS 203 explicitly, record the parameter set (ML-KEM-512, -768, -1024) and hybrid pairing, and follow NIST's migration guidance rather than ad-hac PQ adoption.

## Current context and source status

FIPS 203 was published August 13, 2024, alongside FIPS 204 (ML-DSA signatures) and FIPS 205 (SLH-DSA), completing NIST's first post-quantum standardization round. TLS hybrid key share X25519MLKEM768 is standardized through IETF drafts and deployed in major browsers and CDNs. NIST IR 8547 (transition planning) addresses the deprecation timeline for quantum-vulnerable algorithms; SP 800-227 (KEM recommendations) provides KEM usage guidance.

## Governance pattern

1. Cite FIPS 203 and record the parameter set: ML-KEM-512 (lower security, smallest), ML-KEM-768 (default, TLS's primary choice), ML-KEM-1024 (highest security); parameter set selection is a security decision recorded with rationale.
2. Deploy hybrid by default during the transition: classical (X25519) + ML-KEM combined so the construction is no weaker than classical while PQ maturity develops; pure ML-KEM deployment is a deliberate later decision.
3. Use the standard's encapsulation/decapsulation interface exactly: ML-KEM is a KEM (encapsulate to a public key, derive shared secret), not a Diffie-Hellman exchange or a signature scheme.
4. Bind context per protocol: the shared secret feeds the protocol's KDF with protocol-defined context (TLS 1.3's hybrid key share derivation defines the binding); no shared-secret reuse across protocols.
5. Validate decapsulation outputs per the standard's implicit rejection behavior: ML-KEM's Fujisaki-Okamoto transform defines implicit rejection; implementations must not leak whether rejection occurred.
6. Manage ciphertext malleability expectations: KEM ciphertexts are not authenticated by the KEM itself; authentication comes from the protocol (signed key shares, AEAD confirmation) — record which layer provides it.
7. Track validation: ACVP validates ML-KEM implementations; FIPS-bound deployments require module validation covering ML-KEM at the chosen parameter set.
8. Reproduce the FIPS 203 test vectors before production use.

## Validation and evidence

Evidence includes:

- parameter set selection with rationale recorded per deployment;
- hybrid pairing documentation (classical component and combination mode);
- protocol context binding records;
- module validation certificate covering ML-KEM;
- ACVP results at the chosen parameter set;
- FIPS 203 test vectors reproduced;
- implicit rejection non-leakage verified in implementation review.

## Failure correction

Common defects include:

- Pure ML-KEM deployed where hybrid was the policy, removing the classical floor during the transition.
- Shared secret used without protocol context binding.
- Implementation distinguishing implicit rejection (timing or error code), enabling adaptive attacks.
- Parameter set chosen for size without recording the security rationale.

Corrective actions include hybrid restoration, context binding insertion, rejection non-leakage fixes, and documented parameter re-selection.

## Limitations

FIPS 203 standardizes the mechanism; protocol integration (TLS, IKE, HPKE-style profiles) proceeds through IETF specifications at their own pace. PQ migration planning spans harvest-now-decrypt-later threat assessment per NIST IR 8547's timeline guidance. ML-KEM addresses key establishment only; post-quantum signatures are FIPS 204/205.

## Hybrid transition economics

The hybrid rule exists because two failure modes price asymmetrically: if quantum capability arrives early, pure-classical key exchange breaks catastrophically; if ML-KEM falls to cryptanalysis, pure-PQ deployment breaks. Hybrid constructions cap both risks at the cost of larger key shares — the transition's dominant deployed posture (X25519MLKEM768 in TLS) is exactly this hedge. Retiring the classical leg is a policy decision on cryptanalytic evidence, not a size optimization.

## Canonical sources

- FIPS 203, *Module-Lattice-Based Key-Encapsulation Mechanism Standard* (NIST CSRC, August 2024): https://csrc.nist.gov/pubs/fips/203/final
- FIPS 204, *Module-Lattice-Based Digital Signature Standard* (NIST CSRC): https://csrc.nist.gov/pubs/fips/204/final
- FIPS 205, * Stateless Hash-Based Digital Signature Standard* (NIST CSRC): https://csrc.nist.gov/pubs/fips/205/final
- NIST IR 8547 — Transition to Post-Quantum Cryptography Standards: https://csrc.nist.gov/pubs/ir/8547/ipd
- NIST SP 800-227 — Recommendations for Key-Encapsulation Mechanisms: https://csrc.nist.gov/pubs/sp/800/227/final

Sources were verified on September 2, 2026.
