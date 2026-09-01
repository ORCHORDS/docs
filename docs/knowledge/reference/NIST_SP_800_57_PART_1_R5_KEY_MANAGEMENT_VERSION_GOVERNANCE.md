# NIST SP 800-57 Part 1 Rev. 5 Key Management Version Governance

## Purpose

NIST Special Publication 800-57 Part 1 Revision 5, *Recommendation for Key Management: General* (May 2020), is the current NIST guidance on key-management concepts, cryptographic key types, key lifecycle stages, cryptographic algorithm assurance, and the cryptographic-period policies that determine when operational keys should be replaced or retired. Profiles that govern symmetric, asymmetric, or key-derivation material should reference SP 800-57 Part 1 Rev. 5 explicitly.

The publication does not specify any particular algorithm or protocol. Instead, it defines terminology and lifecycle expectations that, together with the algorithm-specific Special Publications (for example SP 800-56A, SP 800-56B, SP 800-131A), produce a complete key-management profile.

## Current context and source status

SP 800-57 Part 1 Rev. 5 was published in May 2020. It supersedes Part 1 Rev. 4 from January 2016. Companion documents include Part 2 (best practices for key management organizations) and Part 3 (application-specific key management). No successor revision is published as of September 1, 2026, although periodic updates to algorithm-specific Special Publications (for example SP 800-131A) can change the assurance labels that Part 1 references.

## Governance pattern

1. Cite SP 800-57 Part 1 Rev. 5 in key-management policies, key-custodian procedures, lifecycle records, and cryptographic-assurance summaries.
2. Identify the cryptographic-key types in scope (symmetric data-encryption keys, symmetric key-wrapping keys, symmetric authentication keys, public signature keys, public key-establishment keys, ephemeral keys, root and subordinate key-management keys, and authorization keys) and assign the relevant originator-usage period, recipient-usage period, and cryptoperiod limits.
3. Document assurance levels using the deprecation, restricted, acceptable, and legacy classifications defined in SP 800-131A. A profile claiming only "FIPS-validated" without the assurance label is ambiguous.
4. Specify the lifecycle stages in operation (key generation, distribution, storage, use, key change, key update, key archival, key escrow, key recovery, key suspension, key deactivation, key destruction, key revocation, and key compromise) and the records produced at each transition.
5. Maintain an authoritative key inventory that binds each operational key to its algorithm, bit length, lifetime, custodian, and revocation status.
6. Plan replacements and rekeys in advance of cryptoperiod expiration. Do not rely on the cryptographic algorithm to fail loudly at the end of its originator-usage period.
7. Where quantum risk is relevant, document the quantum vulnerability label (for example, integer-factorization and discrete-logarithm schemes are labeled quantum-vulnerable) and the planned transition to post-quantum replacements.
8. Treat symmetric key zeroization as a recorded event rather than as an inferred consequence of file deletion or session termination.

## Key states and transitions

SP 800-57 Part 1 Rev. 5 describes key states (pre-activation, active, suspended, deactivated, compromised, destroyed) and the transitions between them. Procedures should map each state to a specific control, an event log entry, and an authorized role. Cryptographic-period boundaries (the originator-usage period and recipient-usage period) should be enforced through the same state machine rather than only through calendar reminders.

## Validation and evidence

Compliance evidence includes:

- an up-to-date key inventory with algorithm, bit length, state, cryptoperiod, and custodian;
- documented cryptographic-period boundaries and the records that show replacements occurring before expiry;
- signed or recorded key-generation, distribution, and zeroization events;
- algorithm assurance labels traceable to SP 800-131A Rev. 2 or the current revision;
- key-compromise handling procedures with documented timelines and approvers;
- separation of duties between key custodian, key owner, and audit role.

Evidence that omits the assurance label, the state transitions, or the cryptoperiod boundaries does not establish SP 800-57 Part 1 Rev. 5 conformance.

## Failure correction

Common defects include:

- Keys labelled "FIPS" but still using algorithms that SP 800-131A marks as deprecated, restricted, or disallowed.
- Cryptoperiods set to "indefinite" or "until compromise" for keys whose algorithm is at the end of its originator-usage period.
- Key compromise handled through re-installation rather than revocation and replacement of the underlying key material.
- Destroy operations missing because storage subsystems retain keys in caches, swap, or remote backups.

Corrective actions include updating the assurance labels, shortening the cryptoperiod, scheduling rekey events, and re-running the lifecycle procedures with new evidence.

## Limitations

SP 800-57 Part 1 Rev. 5 does not define:

- algorithm implementations, which are governed by FIPS publications and the algorithm-specific Special Publications;
- protocol-specific key exchange, which is governed by SP 800-56A/B or by an Internet Standard such as TLS 1.3;
- post-quantum key management, although the publication's framework supports future algorithms.

## Cryptoperiod planning

Cryptoperiods in SP 800-57 Part 1 Rev. 5 are guidance, not absolutes. Profiles should treat them as the maximum allowed under non-compromise conditions and should shorten them based on:

- volume of use under a given key (for example, AES-GCM nonces after 2^32 operations);
- sensitivity of the protected data (for example, long-term confidentiality requires shorter cryptoperiods for symmetric data-encryption keys);
- exposure of the key to multi-party systems (for example, key-wrapping keys shared across many recipients);
- regulatory or sectoral guidance (PCI DSS, HIPAA, FIPS 140 module policies).

Where the cryptoperiod is bounded by the protocol rather than by calendar time (for example, TLS 1.3 session keys), the protocol's session-resumption and key-update rules should be cross-referenced with the SP 800-57 Part 1 Rev. 5 cryptoperiod guidance.

## Key inventory expectations

Profiles that claim SP 800-57 Part 1 Rev. 5 conformance should maintain a key inventory that records at minimum:

- a stable key identifier (for example, a SHA-256 thumbprint of the key material);
- the algorithm, bit length, and mode of operation;
- the cryptographic-key type from the SP 800-57 Part 1 Rev. 5 taxonomy;
- the originator-usage period and the recipient-usage period;
- the current state (pre-activation, active, suspended, deactivated, compromised, destroyed);
- the custodian, owner, and audit role;
- the archival and recovery policy;
- the destruction event and zeroization method.

A key inventory that omits any of these fields cannot establish that the key management policy follows SP 800-57 Part 1 Rev. 5's lifecycle expectations.

## Canonical sources

- NIST SP 800-57 Part 1 Rev. 5, *Recommendation for Key Management: General* (publication page): https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final
- NIST SP 800-57 Part 1 Rev. 5 (DOI link, NIST Computer Security Resource Center): https://doi.org/10.6028/NIST.SP.800-57pt1r5
- NIST SP 800-131A Rev. 2, *Transitioning the Use of Cryptographic Algorithms and Key Lengths* (companion assurance guidance): https://csrc.nist.gov/pubs/sp/800/131/a/r2/final

Sources were verified on September 1, 2026.
