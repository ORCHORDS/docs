# Subscriber-Controlled Wallet Federation

## Purpose

NIST SP 800-63C-4 adds subscriber-controlled wallets to the federation model. In this architecture, a credential service provider (CSP) issues signed attribute bundles to a wallet controlled by or for the subscriber. The wallet can then act as an identity provider (IdP) when presenting an assertion to a relying party (RP).

This model changes the usual federation trust path. The CSP does not necessarily participate directly in each RP transaction, so wallet activation, attribute-bundle verification, trust agreements, key handling, runtime disclosure, and revocation all become important parts of the assurance decision.

## Basic transaction model

A reusable mental model is:

1. The CSP identity-proofs the subscriber and establishes a subscriber account.
2. The subscriber proves identity or authenticates to the CSP issuance process.
3. The wallet generates or selects a signing key and proves possession of that key to the CSP.
4. The CSP issues one or more signed attribute bundles containing subscriber attributes and a wallet verification key or reference to it.
5. The RP requests a federation transaction from the wallet.
6. The subscriber activates the wallet using the required activation factor.
7. The wallet creates and signs an assertion based on the RP request, subscriber decision, and available attribute bundles.
8. The RP validates the wallet assertion and the CSP-signed attribute bundle before creating an authenticated session.

The wallet is therefore not merely a storage container. In the NIST model it performs IdP functions and participates directly in the federation transaction.

## Attribute-bundle governance

Attribute bundles are signed by the CSP and can contain attributes or derived attribute values. The RP can verify them independently of the wallet's own signature by validating the CSP's cryptographic protection.

Governance should address:

- which attributes a CSP can issue into bundles;
- which attributes or derived values the wallet may disclose;
- the identity-proofing or issuance process represented by the bundle;
- the bundle's validity period and status-checking method;
- whether selective disclosure is supported;
- what RP purposes are allowed for each requested attribute; and
- how compromised, obsolete, or terminated bundles are invalidated.

NIST requires the CSP to provide a means of invalidating issued attribute bundles. Limited validity windows and privacy-preserving status mechanisms reduce the risk of stale or compromised bundles remaining useful indefinitely.

## Runtime subscriber decision

In subscriber-controlled wallet scenarios, release of subscriber attributes is managed through a runtime decision by the wallet, and the subscriber is the authorized party.

Before release, the subscriber should be given understandable, actionable information about:

- the attributes, derived attributes, or bundles requested by the RP; and
- the purpose for each requested attribute.

Do not treat wallet possession as blanket consent for every attribute request. The runtime decision is part of the privacy and trust model.

## Wallet activation

NIST requires an activation factor for actions that create signed artifacts using wallet signing keys, including:

- proving possession of the wallet signing key to the CSP during issuance; and
- signing an assertion for presentation to the RP.

For a wallet running on a subscriber-controlled device, wallet activation is generally a separate operation from simply unlocking the host device, even though the same factor may be used in both operations where the NIST conditions are met.

For remotely hosted wallets, activation is performed using an authenticator registered to the wallet service.

## Signing-key boundary

Wallet signing keys used for assertions have a different lifecycle from ordinary synchronized authentication credentials.

SP 800-63C-4 states that keys used for signing assertions SHALL NOT be synced or shared across devices and recommends non-exportable key storage. If the wallet signing key is used for a holder-of-key assertion at FAL3, non-exportable storage is required.

This distinction is important: a platform may support both synchronized passkeys and a subscriber-controlled wallet, but the assurance properties of those keys are not interchangeable.

## Trust agreements

Wallet federation can involve several trust relationships:

### CSP and wallet

The CSP and wallet have a direct trust relationship. Their agreement should define at least:

- attributes and derived attributes available in bundles;
- attributes the wallet may release to RPs;
- issuance-process requirements imposed on the wallet;
- wallet data-storage and security practices;
- activation methods or assurance levels used before assertions are generated;
- supported federation assurance levels; and
- permitted purposes or release restrictions.

### CSP and RP

The RP needs confidence in the CSP's attribute-bundle issuance process even though the CSP may not know the RP directly. This can be established through bilateral configuration, published CSP information, or a federation authority and multilateral trust agreement.

### Wallet and RP

The RP needs information about the wallet capabilities that affect transaction trust. NIST requires subscriber-controlled wallets to disclose information including activation or authentication methods, protection of attribute bundles, key-management information, and indications of wallet software integrity.

## Discovery and verification

Before accepting a federation transaction, the RP needs a secure way to determine the CSP verification key used for attribute bundles. Depending on the ecosystem, this may use:

- a CSP-controlled discovery location;
- manual configuration;
- a federation authority; or
- another trusted discovery and registration service defined by the trust agreement.

The RP should validate both layers of the transaction:

1. the wallet's assertion and proof of its signing key; and
2. the CSP signature and status of the attribute bundle carried by that assertion.

## FAL boundary

Do not infer a Federation Assurance Level merely from the presence of a wallet.

A subscriber-controlled wallet on a subscriber-controlled device can potentially create holder-of-key assertions suitable for FAL3 when all FAL3 and holder-of-key requirements are met. A remotely hosted wallet does not meet that condition merely because it has its own verification key; an additional holder-of-key or bound-authenticator mechanism is required for FAL3 as specified by NIST.

Document the actual transaction properties used to justify the claimed federation assurance level.

## Operational lifecycle

A wallet federation design should define:

- issuance and reissuance of attribute bundles;
- subscriber activation and recovery;
- wallet loss or device replacement;
- compromise response;
- bundle expiration and revocation;
- CSP or subscriber-account termination;
- RP trust-list or discovery updates;
- signing-key rotation; and
- removal of wallet authorization.

Loss of a device, termination of a subscriber account, or compromise of an attribute bundle should not leave downstream federation artifacts valid indefinitely.

## Evidence to retain

Where appropriate, retain:

- applicable FAL and transaction assumptions;
- CSP/wallet/RP trust-agreement terms;
- attribute-bundle schema and issuance rules;
- wallet activation requirements;
- signing-key protection requirements;
- CSP verification-key discovery method;
- revocation/status design;
- allowed RP purposes for attributes;
- interoperability and negative-test results; and
- version/date of the NIST guidance used for the design review.

## Sources

- NIST SP 800-63C-4 — Federation and Assertions: https://pages.nist.gov/800-63-4/sp800-63c.html
- NIST SP 800-63 Revision 4 publication hub: https://pages.nist.gov/800-63-4/

## Scope note

This article summarizes reusable architecture and governance considerations from NIST SP 800-63C-4. It does not claim that any specific wallet, credential, identity provider, relying party, or ORCHORDS system achieves a particular FAL or conforms to NIST requirements.