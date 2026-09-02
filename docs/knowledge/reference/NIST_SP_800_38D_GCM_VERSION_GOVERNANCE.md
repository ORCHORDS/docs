# NIST SP 800-38D GCM Version Governance

## Purpose

NIST SP 800-38D, *Recommendation for Block Cipher Modes of Operation: Galois/Counter Mode (GCM) and GMAC* (November 2007), specifies GCM: an authenticated encryption mode built from a block cipher in counter mode with a GHASH-based authentication tag, and GMAC, its authentication-only form.

Implementations using AES-GCM should cite SP 800-38D explicitly, record tag lengths and IV construction, and enforce the standard's crucial usage constraint: the IV-generation method and the per-key invocation limit.

## Current context and source status

SP 800-38D was published November 2007 and remains the governing recommendation for GCM. It was amended by SP 800-38D Addendum on IV requirements (October 2009) clarifying deterministic IV construction for high-volume encryption per key. AES-GCM is validated through CAVP/ACVP under the AES-GCM algorithm. IETF RFC 5116 formalizes AEAD interface conventions for GCM.

## Governance pattern

1. Cite SP 800-38D and record the construction: AES-GCM with the key size (128/192/256) and the tag length; supported tag lengths are 128, 120, 112, 104, 96, 64, and 32 bits, with at least 96 bits recommended for most uses and shorter tags explicitly justified.
2. Construct IVs per the approved method: random 96-bit IVs, or deterministic construction per the 38D Addendum; record the method per key.
3. Enforce the invocation limit: with random IVs, the probability of IV collision must be bounded (the standard frames 2^32 random-IV invocations per key as the ceiling for safety); a per-key counter that halts at the limit is a control, not an optimization.
4. Never reuse an IV with the same key; IV reuse under GCM is catastrophic — it reveals the authentication key (H) and the XOR of plaintexts. This is the single most important GCM control.
5. Use GHASH correctly for non-96-bit IVs: the standard's algorithm converts arbitrary IV lengths; implementations must not substitute ad-hoc IV handling.
6. For GMAC (authentication only), apply the same IV discipline; GMAC shares GCM's authentication internals and its IV-reuse failure mode.
7. Reject unauthenticated plaintext before any release: decryption outputs plaintext and tag together; releasing plaintext before tag verification is the classic implementation defect.
8. Reproduce the SP 800-38D test vectors and validate AES-GCM through ACVP for the key size and tag length used.

## Validation and evidence

Evidence includes:

- key size, tag length, and IV method recorded per service in the module policy;
- per-key invocation counters with halt thresholds;
- module validation certificate covering AES-GCM;
- ACVP results for the parameter set;
- code review evidence that plaintext release is gated on tag verification;
- IV-generation documentation for random and deterministic methods.

## Failure correction

Common defects include:

- IV reuse under the same key, exposing the authentication key and plaintext XORs.
- Invocation limits unenforced, allowing birthday-bound IV collisions in high-volume keys.
- Plaintext released before tag verification (timing or API design flaw).
- Tag length reduced below 96 bits without recorded justification.

Corrective actions include immediate key rotation on suspected IV reuse, invocation counter enforcement, API redesign to withhold plaintext until verification, and tag length restoration.

## Limitations

SP 800-38D does not define:

- key derivation or key hierarchy; SP 800-108 governs KDFs;
- nonce-misuse resistance; SIV modes (RFC 5297, SP 800-38D's sibling 800-38F for key wrap) address misuse-resistant constructions;
- non-AES block ciphers' GCM profiles; 38D is AES-centric.

GCM is an AEAD mode, not a hash, KDF, or signature scheme.

## Invocation-limit discipline

The birthday bound governs random-IV GCM safety: with 96-bit random IVs, collision probability crosses uncomfortable thresholds near 2^32 encryptions per key. Long-lived keys encrypting high volumes must either rotate before the bound or use the deterministic IV construction from the 38D Addendum with a monotonic counter. Per-key invocation counters with halt thresholds are the operational control; exceeding the bound without detection is a silent integrity failure, not a crash.

## Canonical sources

- NIST SP 800-38D, *Recommendation for Block Cipher Modes of Operation: Galois/Counter Mode (GCM) and GMAC* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/38d/final
- NIST SP 800-38D Addendum, *IV Requirements for GCM* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/38d/upd1/final
- RFC 5116, *An Interface and Algorithms for Authenticated Encryption* (RFC Editor): https://www.rfc-editor.org/rfc/rfc5116
- NIST SP 800-38F, *Recommendation for Block Cipher Modes of Operation: Methods for Key Wrapping* (misuse-resistant comparison): https://csrc.nist.gov/pubs/sp/800/38f/final
- NIST — CAVP AES-GCM validation: https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program

Sources were verified on September 2, 2026.
