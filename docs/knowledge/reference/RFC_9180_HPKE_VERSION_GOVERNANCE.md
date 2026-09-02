# RFC 9180 HPKE Version Governance

## Purpose

RFC 9180, *Hybrid Public Key Encryption* (February 2022), specifies HPKE: a scheme for public key encryption of arbitrary-sized plaintexts built from a non-interactive Diffie-Hellman key exchange, a KDF, and an AEAD. HPKE underlies ECH (Encrypted Client Hello) in TLS, MLS messaging, and many modern envelope-encryption protocols.

Implementations using HPKE should cite RFC 9180 explicitly, record the chosen DH group, KDF, and AEAD from the IANA registries, and bind context (application info and exporter secrets) deliberately.

## Current context and source status

RFC 9180 was published in February 2022 as a Standards Track RFC (Proposed Standard). RFC 9180 is not obsoleted; errata are tracked by the CFRG. Companion specifications profile HPKE for specific uses (TLS ECH, MLS RFC 9420, COSE profiles in the RFC 9052/9053 family). IANA maintains the HPKE KEM/KDF/AEAD identifier registries.

## Governance pattern

1. Cite RFC 9180 explicitly and record the ciphersuite as the registered identifier triple: KEM (for example 0x0020 P-256), KDF (0x0001 HKDF-SHA256), AEAD (0x0001 AES-128-GCM).
2. Select the KEM by platform and threat model: elliptic-curve KEMs (P-256, P-521, X25519, X448) for classical deployments; the post-quantum hybrid KEMs enter through later RFCs and registry extensions and must not be hand-rolled.
3. Use the single-shot or streaming API per the message pattern; do not re-implement the context setup (KeySchedule) outside a conformant implementation.
4. Bind application context through the `info` parameter at setup and derive domain-separated keys with the Export interface (`secret_export`) rather than reusing the base secret.
5. For long-lived recipients, rotate keys and record epoch boundaries; HPKE has no rekeying built in — rotation is new context establishment.
6. Authenticate the sender where the protocol requires it: core HPKE hides the sender identity by design; protocols needing sender authentication layer a signature or PSK mode over it.
7. Reproduce the RFC 9180 test vectors (Appendix A) for the chosen ciphersuite before production use.

## Validation and evidence

Evidence includes:

- ciphersuite identifiers recorded per deployment with KEM/KDF/AEAD names;
- context binding records: `info` strings and exporter purposes enumerated;
- key rotation records with epoch boundaries;
- sender authentication decision documented where required by the protocol;
- RFC 9180 Appendix A test vectors reproduced;
- library/implementation version recorded in the cryptographic module policy.

## Failure correction

Common defects include:

- Reusing the base secret across purposes instead of deriving per-purpose keys via Export.
- Omitting the `info` context, collapsing separation between protocols that share a recipient key.
- Hand-rolling the KeySchedule instead of using a conformant implementation, producing interop failures or subtle weakening.
- Assuming sender authentication exists because ciphertexts verify; core HPKE authenticates the recipient key only.

Corrective actions include moving to exporter-derived keys, defining info strings per protocol, adopting a conformant library, and layering authentication where the protocol needs it.

## Limitations

RFC 9180 does not define:

- sender authentication (except via PSK or Auth variants layered by the caller);
- post-quantum security with the original KEM identifiers; PQ hybrids arrive through registry extension and later specifications;
- message padding or traffic-analysis resistance beyond AEAD overhead.

HPKE is an encryption construction, not a full messaging protocol; MLS and ECH define the protocol layers above it.

## Exporter discipline

The Export interface derives additional secrets bound to the HPKE context. Each derived purpose uses a distinct exporter label; exporter labels follow the same discipline as HKDF info strings — a change in label is a protocol change requiring new test vectors. Do not export the same label for two purposes, and never use the raw shared secret outside KeySchedule and Export.

## Canonical sources

- RFC 9180, *Hybrid Public Key Encryption* (RFC Editor): https://www.rfc-editor.org/rfc/rfc9180
- RFC 9459, *CBOR Object Signing and Encryption (COSE): AES-CTR and AES-CBC* (RFC Editor, related COSE profiles): https://www.rfc-editor.org/rfc/rfc9459
- RFC 9420, *The Messaging Layer Security (MLS) Protocol* (RFC Editor, HPKE usage): https://www.rfc-editor.org/rfc/rfc9420
- IANA — HPKE registries: https://www.iana.org/assignments/hpke/
- NIST SP 800-56A Rev 2, *Recommendation for Pair-Wise Key Establishment Schemes Using Discrete Logarithm Cryptography*: https://csrc.nist.gov/pubs/sp/800/56a/r2/final

Sources were verified on September 2, 2026.
