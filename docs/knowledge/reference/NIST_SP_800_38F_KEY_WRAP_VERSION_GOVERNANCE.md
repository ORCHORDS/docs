# NIST SP 800-38F Key Wrap Version Governance

## Purpose

NIST SP 800-38F, *Recommendation for Block Cipher Modes of Operation: Methods for Key Wrapping* (December 2012), specifies the AES Key Wrap (KW), AES Key Wrap with Padding (KWP), and TDEA Key Wrap modes for protecting cryptographic keys at rest or in transport — wrapping keys with a key-encryption key through an integrity-protected construction.

Implementations wrapping keys should cite SP 800-38F explicitly, record the mode (KW or KWP) and the key-encryption key's provenance, and treat the wrap/unwrap pair as a governed lifecycle boundary.

## Governance pattern

1. Cite SP 800-38F and record the mode: KW for inputs that are multiples of the block size (typical for symmetric keys), KWP for arbitrary-length inputs.
2. Source key-encryption keys deliberately: a KEK is generated or established per SP 800-57 guidance, never derived from a password for this purpose (password-based derivation belongs to SP 800-132 paths).
3. Treat key wrapping as a lifecycle event: wrap on export/backup/transfer, unwrap on import/use; each event records which key, under which KEK, by which service.
4. Prefer direct AES-GCM encryption of key material to SP 800-38F wrapping only when the use case needs a dedicated key-transport semantic; for storage encryption inside a validated module, KW/KWP per 38F is the conformant construction.
5. Verify integrity on unwrap: key wrap's IV (the default A6A6... initial value) functions as an integrity check; failed unwrap returns an error and never emits candidate key material.
6. Rotate KEKs on the key-management schedule; re-wrap wrapped keys under the new KEK as a controlled migration with verification, not bulk re-wrap without checks.
7. Never wrap a key under itself or create wrap cycles; KEK hierarchies are acyclic and documented.
8. Reproduce SP 800-38F test vectors and validate through ACVP for the mode used.

## Validation and evidence

Evidence includes:

- mode (KW/KWP) and KEK provenance recorded per wrapping service;
- wrap/unwrap event logs with key identifiers and KEK identifiers;
- KEK rotation and re-wrap migration records with verification steps;
- KEK hierarchy documentation showing acyclicity;
- ACVP validation and test vector reproduction.

## Failure correction

Common defects include:

- Unwrap failures ignored or partially unwrapped key material used.
- KEKs shared across environments beyond their intended scope.
- Wrap cycles or self-wrapping introduced during migrations.
- Arbitrary-length inputs forced through KW (block-size multiple required) with ad-hoc padding instead of KWP.

Corrective actions include fail-closed unwrap handling, KEK scope reduction, hierarchy reconstruction, and KWP adoption for variable-length inputs.

## Limitations

SP 800-38F wraps symmetric key material; it is not an AEAD for general data (GCM's scope) nor a public-key envelope (HPKE's scope). The construction protects confidentiality and integrity of the wrapped key given KEK protection; KEK compromise unwraps everything under it — KEK governance is the real security boundary.

## KEK hierarchy discipline

Key wrap operates within a hierarchy: root KEKs wrap KEKs, KEKs wrap operational keys. The hierarchy must be documented (which key wraps which), acyclic, and refreshed on schedule. The most common operational failure is hierarchy drift during migrations: a re-wrap leaves the old wrapping in place, creating two live paths to the same operational key. Re-wrap migrations end with verification that exactly one path exists per key.

## Canonical sources

- NIST SP 800-38F, *Recommendation for Block Cipher Modes of Operation: Methods for Key Wrapping* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/38f/final
- RFC 3394, *Advanced Encryption Standard (AES) Key Wrap Algorithm* (RFC Editor, KW counterpart): https://www.rfc-editor.org/rfc/rfc3394
- RFC 5649, *AES Key Wrap with Padding Algorithm* (RFC Editor, KWP counterpart): https://www.rfc-editor.org/rfc/rfc5649
- NIST SP 800-57 Part 1 Rev 5, *Key Management Guidance* (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/57/part1/r5/final
- NIST — ACVP key wrap validation: https://csrc.nist.gov/projects/cryptographic-algorithm-validation-program

Sources were verified on September 2, 2026.
