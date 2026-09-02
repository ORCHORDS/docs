# RFC 5297 AES-SIV Version Governance

## Purpose

RFC 5297, *Synthetic Initialization Vector (SIV) Authenticated Encryption Using the Advanced Encryption Standard (AES)* (October 2008), specifies AES-SIV: a misuse-resistant authenticated encryption mode that derives the IV from the plaintext and key, so nonce reuse reveals only whether the exact plaintext was repeated — never the catastrophic authentication-key compromise that GCM nonce reuse causes.

Implementations needing nonce-misuse resistance should cite RFC 5297 explicitly, record the key sizes and associated-data handling, and understand SIV's trade-offs versus GCM.

## Current context and source status

RFC 5297 was published October 2008 as an Informational RFC and is not obsoleted. NIST SP 800-38D addresses GCM (misuse-sensitive); SIV's misuse-resistance profile motivated its adoption in deterministic-storage encryption and key wrapping contexts. A related NIST mode, AES-XTS (SP 800-38E), serves sector-based storage; SIV serves message encryption where deterministic or misuse-resistant semantics are required. RFC 8446's TLS 1.3 uses SIV nowhere by default — SIV adoption is application-layer.

## Governance pattern

1. Cite RFC 5297 and record the construction: AES-CMAC for the synthetic IV, AES-CTR for encryption, with key lengths (S2V key and CTR key, 128 or 256 each).
2. Use SIV where misuse resistance is the requirement: deterministic encryption for stable-plaintext storage lookups, key wrapping variants, or protocols where nonce management cannot be guaranteed; do not default to SIV where GCM's nonce discipline is already enforced — SIV costs roughly double the AES operations.
3. Pass associated data through the S2V input: SIV supports multiple associated-data components (including a header/nonce as AD component); record which components the protocol binds.
4. Use the deterministic form (zero-length nonce component) deliberately: identical plaintext plus identical AD yields identical ciphertext — the property deterministic-storage wants and traffic-analysis-sensitive protocols must avoid.
5. Do not truncate or substitute the synthetic IV; the 128-bit S2V output is both the IV and half the tag.
6. Verify the tag before releasing plaintext (the first block of the tag is the SIV comparison); implementations must fail closed.
7. Reproduce RFC 5297's test vectors (Appendix A) before production use, including the deterministic and nonce-based cases.

## Validation and evidence

Evidence includes:

- construction and key lengths recorded per service;
- misuse-resistance rationale documented where SIV is selected;
- associated-data component list per protocol;
- deterministic-form decision recorded with traffic-analysis consideration;
- fail-closed verification evidence;
- RFC 5297 Appendix A vectors reproduced.

## Failure correction

Common defects include:

- SIV selected for throughput-sensitive paths without acknowledging the two-pass cost.
- Deterministic form used where plaintext repetition is a confidentiality leak the protocol cannot accept.
- Associated data omitted, removing protocol binding.
- Tag verification implemented after plaintext release.

Corrective actions include mode re-selection with rationale, AD component definition, deterministic-vs-nonce re-decision, and fail-closed verification fixes.

## Limitations

RFC 5297 is not a NIST-recommended mode in SP 800-38D's sense; FIPS validation scope should be checked before FIPS-bound use. SIV is not a stream cipher or a KDF. Its misuse resistance covers nonce reuse, not key reuse across protocols or side-channel exposure.

## Misuse-resistance economics

GCM's catastrophic failure mode (nonce reuse → authentication key recovery) is an operational risk that SIV converts into a benign one (repetition equality leak). The trade is performance (SIV is two-pass) and stream-parallelism limits. The decision rule: where nonces are managed by a single disciplined component, GCM with enforced invocation limits is efficient and sound; where nonces cross trust boundaries or stateless encryptors exist, SIV's misuse resistance is the safer architecture.

## Canonical sources

- RFC 5297, *Synthetic Initialization Vector (SIV) Authenticated Encryption Using the Advanced Encryption Standard (AES)* (RFC Editor): https://www.rfc-editor.org/rfc/rfc5297
- RFC 5116, *An Interface and Algorithms for Authenticated Encryption* (RFC Editor): https://www.rfc-editor.org/rfc/rfc5116
- NIST SP 800-38D, *GCM and GMAC* (NIST CSRC, misuse-sensitive comparison): https://csrc.nist.gov/pubs/sp/800/38d/final
- NIST SP 800-38F, *Methods for Key Wrapping* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/38f/final
- RFC 8446, *TLS 1.3* (RFC Editor, context on AEAD usage): https://www.rfc-editor.org/rfc/rfc8446

Sources were verified on September 2, 2026.
