# FIPS 197 AES Governance

## Purpose

FIPS 197, *Advanced Encryption Standard (AES)*, is the United States National Institute of Standards and Technology (NIST) Federal Information Processing Standard that specifies the AES algorithm adopted in November 2001. The algorithm is a symmetric block cipher operating on 128-bit blocks with key sizes of 128, 192, or 256 bits, derived from the Rijndael algorithm selected after an open international competition.

This article summarizes a governance pattern for selecting, deploying, and operating AES in a way consistent with FIPS 197 and the related NIST algorithm-transition and validation guidance. It does not assert conformity to any specific U.S. federal requirement, replace FIPS 197 itself, or substitute for the underlying mathematics; it focuses on the operational and engineering decisions that surround the standard.

## Scope

FIPS 197 specifies the AES algorithm. It does not by itself cover modes of operation, padding, key management, or implementation environment, which are addressed in adjacent NIST publications:

- NIST SP 800-38A — recommended block cipher modes (ECB, CBC, CFB, OFB, CTR);
- NIST SP 800-38D — Galois/Counter Mode (GCM);
- NIST SP 800-38F — key-wrapping modes;
- NIST SP 800-131A Rev. 2 — cryptographic algorithm and key-length transitions;
- NIST SP 800-133 Rev. 2 — cryptographic key generation;
- FIPS 140-3 — cryptographic module validation;
- FIPS 186-5 — digital signatures (which can be combined with AES for hybrid schemes).

A program should document which of these adjacencies are in scope, since FIPS 197 on its own is rarely the only relevant standard for an AES deployment.

## Workflow

A reusable FIPS 197 program runs as a cycle.

1. **Identify AES use cases.** Inventory every use of AES, including data at rest, data in transit, message authentication via AES-GCM, file and disk encryption, full-disk or volume encryption, and key wrapping.
2. **Select key size and mode.** Choose a key size (128, 192, or 256 bits) appropriate to the protection need, threat model, and any applicable policy. Choose a mode of operation appropriate to the use case.
3. **Select a validated module.** Use AES only through a FIPS-validated cryptographic module when regulated data is involved. Note the version, certificate, and Security Policy of the module.
4. **Establish key-management practice.** Generate, distribute, store, rotate, and destroy keys according to NIST SP 800-133 Rev. 2 and the relevant application-level guidance.
5. **Integrate correctly.** Use a mode that provides the protection property required (for example, GCM for authenticated encryption; never ECB for arbitrary plaintext). Use unique nonces for AES-GCM where required.
6. **Validate the deployed configuration.** Confirm that the algorithm, key size, and mode actually used match the documented design.
7. **Monitor transitions.** Track NIST deprecation notices and cryptographic advisories, and plan transitions well before published deadlines.

## Controls and evidence

A program should map its controls to the decisions FIPS 197 and adjacent publications describe, and retain evidence that those decisions are in force.

| Decision area | Example controls | Example evidence |
|---|---|---|
| Algorithm choice | Approved AES variants only | Module configuration, scan output |
| Key size | 128/192/256-bit AES only | Key-management system inventory, configuration records |
| Mode of operation | Approved mode (e.g., GCM, CBC with HMAC, or XTS for storage) | Configuration records, design documents |
| Module validation | Use only through FIPS-validated module | CMVP certificate, module Security Policy |
| Key management | Generation, distribution, rotation, destruction | Key-management system logs, procedure documents |
| Authentication of ciphertext | AEAD or MAC | Design records, configuration evidence |
| Transition tracking | Migration of deprecated modes/keys | Tracker, transition plan |

For each AES deployment, retain at minimum: the design rationale (algorithm, mode, key size, module); the configuration as deployed; the validation evidence; the key-management procedure; and any exception, with reason, approver, compensating control, and expiry.

## Validation

Validation confirms that AES is being used correctly. Useful activities include:

- reviewing the deployed configuration against the design rationale to confirm algorithm, key size, and mode match;
- scanning binaries and configuration for direct use of AES in disallowed modes (notably ECB for arbitrary plaintext);
- reviewing the nonce or IV generation mechanism for the mode in use (for example, that AES-GCM invocations use a unique nonce from an approved construction);
- running module self-tests and confirming they pass;
- reviewing key-management logs for evidence that keys are generated, rotated, and destroyed as documented; and
- inspecting a sample of ciphertext and confirming that it is not visibly patterned (a common symptom of misuse).

Validation must distinguish compliant, non-compliant, and unable-to-assess states. A configuration that cannot be inspected (for example, because of proprietary opaque storage) is not automatically compliant.

## Failure correction

When an AES control fails, follow a documented path.

1. Confirm the failure with reproducible evidence.
2. Identify whether the failure is in algorithm choice, mode selection, nonce/IV construction, key management, or module integration.
3. Apply the corrective change through the change management process.
4. Verify with new evidence rather than a closed ticket.
5. Update the design rationale if the failure reveals an unrealistic constraint.

Common failure modes include:

- using AES-ECB to encrypt variable-length or structured data, producing patterns visible in the ciphertext;
- reusing a GCM nonce across messages under the same key, which can recover the authentication key in modern exploitations;
- relying on key wrapping alone for confidentiality when the wrapping key is itself inadequate;
- using a vendor library that silently falls back to non-AES algorithms or to non-approved modes;
- generating AES keys from a non-approved random source; and
- rotating data-encryption keys without re-encrypting the data, leaving protected data effectively tied to old keys.

## Limitations

FIPS 197 specifies a single algorithm. The security of a deployment depends on the surrounding choices: mode of operation, padding, key management, source of randomness, and module validation. Even a correctly implemented AES does not protect against misuse, replay, key disclosure, or side-channel attacks on the host platform.

The publication also does not address quantum-resilience considerations. NIST is standardizing post-quantum cryptography in a separate program (FIPS 203, FIPS 204, FIPS 205). Organizations planning long confidentiality lives for AES-protected data should treat the data's confidentiality as conditional on a future migration to quantum-resistant cryptography for the key-exchange or key-encryption layer.

## Canonical sources

- FIPS 197 — *Advanced Encryption Standard (AES)*, final, November 2001: https://csrc.nist.gov/pubs/fips/197/final
- NIST DOI mirror for FIPS 197: https://doi.org/10.6028/NIST.FIPS.197
- NIST SP 800-131A Rev. 2 — *Transitioning the Use of Cryptographic Algorithms and Key Lengths* (algorithm transition policy adjacent to FIPS 197): https://csrc.nist.gov/pubs/sp/800/131/a/r2/final
- FIPS 140-3 — *Security Requirements for Cryptographic Modules* (module validation context for AES): https://csrc.nist.gov/pubs/fips/140-3/final

## Scope note

This article summarizes reusable governance practices derived from FIPS 197 and adjacent NIST publications. It is not a substitute for FIPS 197 itself, does not assert conformity with any U.S. federal cryptographic requirement, and does not constitute legal or compliance advice for any specific deployment.
