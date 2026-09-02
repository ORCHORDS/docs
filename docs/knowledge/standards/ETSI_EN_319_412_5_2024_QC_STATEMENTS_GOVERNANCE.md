# ETSI EN 319 412-5:2024 Qualified Certificate Statements Governance

## Purpose

ETSI EN 319 412-5:2024, "Electronic Signatures and Infrastructures (ESI); Certificate Profiles; Part 5: QCStatements," defines the certificate profile for qualified certificates under the eIDAS Regulation. The standard specifies the QCStatements extension, the statements the TSP must include in qualified certificates, and the relationship to the qualified certificate profile. This article governs the application of EN 319 412-5 so a TSP issuing qualified certificates produces certificate profiles that meet the eIDAS requirements.

## Scope

The standard applies to TSPs issuing qualified certificates under eIDAS. Within this knowledge base, the article covers the QCStatements extension structure, the statements the standard defines (QcCompliance, QcSSCD, QcType, QcPDS, QcRetentionPeriod), the encoding rules, and the verification of qualified certificates. It does not cover the certificate lifecycle (readers should consult EN 319 411 for that).

## Workflow

1. Establish the qualified certificate policy: the certificate types, the qualified certificate requirements, and the relationship to the certificate policy and practice statement.
2. Implement the QCStatements extension per the standard:
   - QcCompliance: indicates the certificate is issued as a qualified certificate under eIDAS.
   - QcSSCD: indicates the private key is held in a qualified signature creation device (QSCD).
   - QcType: indicates the certificate type (e.g., natural person, legal person).
   - QcPDS: provides a pointer to the certificate practice statement or other disclosures.
   - QcRetentionPeriod: indicates the retention period for the certificate information after expiration.
3. Encode the QCStatements in the certificate profile using the ASN.1 encoding defined in the standard.
4. Verify the QCStatements in qualified certificates received from the TSP or from third parties.
5. Document the QCStatements implementation, the certificate profile, and the verification process.

## Controls and evidence

QCStatements controls include the documented implementation, the certificate profiles, the encoding rules, and the verification records. Each qualified certificate should be traceable to the QCStatements implementation.

## Validation

Validation should confirm the QCStatements are implemented correctly, the certificate profile is valid, the encoding is correct, and the verification operates. Audit and conformity assessment confirm the TSP's eIDAS compliance.

## Failure correction

Common failure modes: QCStatements are missing or incorrectly encoded (correct: implement per the standard); the QSCD indication is included without the key being in a QSCD (correct: only include QcSSCD when the key is in a QSCD); QcPDS is not informative (correct: provide a current PDS URL); verification does not parse the QCStatements (correct: implement the verification per the standard).

## Limitations

ETSI EN 319 412-5 specifies the QCStatements profile; it does not certify any TSP's qualified certificates outside the conformity assessment. The standard depends on the broader certificate profile and lifecycle (EN 319 411). The standard does not replace national law.

## Scope note

This article summarizes project-neutral standards use of ETSI EN 319 412-5:2024. It does not assert any specific TSP's conformance or claim any certification outcome.

## Canonical sources

- ETSI EN 319 412-5:2024 — Certificate Profiles; Part 5: QCStatements: https://www.etsi.org/deliver/etsi_en/319400_319499/31941205/