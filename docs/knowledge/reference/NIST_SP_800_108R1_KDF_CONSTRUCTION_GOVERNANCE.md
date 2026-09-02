# NIST SP 800-108 Rev 1 Key Derivation Construction Governance

## Purpose

NIST SP 800-108 Rev 1, *Recommendation for Key Derivation Using Pseudorandom Functions* (updated May 2022 as SP 800-108 Rev 1), specifies key derivation functions in counter mode, feedback mode, and double-pipeline iteration mode for deriving keys from a key-derivation key using an approved PRF (typically HMAC with an approved hash).

Implementations deriving keys within FIPS scope should cite SP 800-108 Rev 1 explicitly, record the mode, PRF, and the fixed input data layout (label, context, IV/L), and enforce the iteration criteria.

## Current context and source status

SP 800-108 Rev 1 was finalized in May 2022 (Update 1), superseding the 2009 original. The revision retains the three modes, clarifies input construction and counter handling, and extends guidance to additional PRFs. ACVP validates KDF modes under SP 800-108. Related: HKDF (RFC 5869) serves similar purposes in IETF protocols but is a different construction; SP 800-56C Rev 2 governs KDFs for key establishment.

## Governance pattern

1. Cite SP 800-108 Rev 1 and record the mode: counter, feedback, or double-pipeline; counter mode is the common default for fixed-output derivation.
2. Record the PRF and its hash (HMAC-SHA-256 typical); the PRF must be an approved PRF in the module's validation scope.
3. Construct the fixed input data deliberately: label (identifying derivation purpose), context (binding information such as algorithm identifiers and parties), and IV/L where the mode uses them; the label+context separation is the domain-separation mechanism — changes are protocol changes.
4. Derive per-purpose keys with distinct labels; one derivation output reused across purposes defeats the standard's separation model.
5. Enforce the iteration criteria: for counter mode, the output length and PRF output size determine the iteration count; implementations must follow the standard's counting, not truncate-and-repeat ad-hoc.
6. Source the key-derivation key properly: it is itself a key (from key establishment, per SP 800-56C where applicable, or generation), never raw key material from outside a validated module.
7. Record output key length and target key usage per derivation; a derivation without recorded purpose and length is ungoverned.
8. Validate through ACVP for the mode and PRF; reproduce the published test vectors.

## Validation and evidence

Evidence includes:

- mode, PRF, and hash recorded per derivation service;
- fixed input data layout documented with label and context conventions;
- per-purpose label registry showing uniqueness;
- key-derivation key provenance records;
- ACVP validation results for the mode/PRF;
- output length and usage records per derivation.

## Failure correction

Common defects include:

- Context omitted, collapsing separation between derivations that share a KDK.
- Labels reused across purposes or informally extended ("v2" suffixes) without registry discipline.
- Ad-hoc output extension (hashing the output again) instead of the standard's iteration.
- KDK sourced from unvalidated randomness or a non-key source.

Corrective actions include context definition, label registry enforcement, iteration-mode conformance, and KDK provenance correction with re-derivation.

## Limitations

SP 800-108 governs KDFs within FIPS scope; IETF protocols commonly use HKDF (RFC 5869), which is a distinct construction with its own citation. Password-based derivation is SP 800-132's scope; SP 800-108 derives from a key, not a password.

## Label and context discipline

The label identifies what the key is for; the context binds instance-specific data. A label registry — enumerating every label in use, its purpose, and its owner — is the operational control that keeps derivations separated as systems grow. Changing a context definition or introducing a new label requires the same review as a protocol change, because derivation collisions are silent.

## Canonical sources

- NIST SP 800-108 Rev 1, *Recommendation for Key Derivation Using Pseudorandom Functions* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/108/upd1/final
- RFC 5869, *HMAC-based Extract-and-Expand Key Derivation Function (HKDF)* (RFC Editor, IETF counterpart): https://www.rfc-editor.org/rfc/rfc5869
- NIST SP 800-132, *Recommendation for Password-Based Key Derivation* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/132/final
- NIST SP 800-56C Rev 2, *Recommendation for Key-Derivation Methods in Key Establishment Schemes*: https://csrc.nist.gov/pubs/sp/800/56c/r2/final
- NIST — ACVP KDF validation: https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program

Sources were verified on September 2, 2026.
