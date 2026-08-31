# Federation Attribute-Bundle Lifecycle

## Purpose

NIST SP 800-63C-4 defines attribute bundles as CSP-signed collections of subscriber attributes or derived attribute values that can be presented to relying parties (RPs) through federation transactions. They are especially important in subscriber-controlled wallet architectures because the RP may receive an assertion from a wallet while independently relying on the credential service provider's signature over the underlying attributes.

Attribute bundles need their own lifecycle governance. Issuance, wallet binding, validity, selective disclosure, RP verification, status checking, invalidation, privacy, and termination all affect whether an attribute received in a federation transaction should still be trusted.

## Attribute-bundle boundary

An attribute bundle is not the same thing as the wallet assertion that carries or references it.

The CSP signs the bundle. The wallet or IdP can then include that bundle, or information derived from it, in an assertion sent to the RP. The RP therefore needs to validate both relevant trust layers:

1. the assertion and the party that created it; and
2. the CSP signature and validity of the attribute bundle itself.

Do not treat a valid wallet signature as proof that every attribute carried by the transaction was issued or remains valid under the CSP's authority.

## Issuance workflow

A reusable issuance pattern is:

1. The subscriber completes the CSP's required identity-proofing and account process.
2. The subscriber authenticates or otherwise proves entitlement to receive a new attribute bundle.
3. The receiving wallet establishes or selects the key material required by the federation design.
4. The wallet proves possession of the applicable key when required.
5. The CSP determines the attributes or derived values authorized for issuance.
6. The CSP creates and signs the bundle, binding it to the appropriate wallet verification key or identifier where required by the profile.
7. The bundle is delivered to the requesting wallet through a protected exchange.
8. The CSP retains the information needed to support later status, invalidation, audit, and subscriber-account management.

Issuance should not become an unrestricted export of every attribute held by the CSP. Release should follow the trust agreement, privacy assessment, and purpose limitations for the wallet ecosystem.

## Bundle uniqueness

SP 800-63C-4 requires a separate attribute bundle for each requesting wallet and recommends that each bundle be unique to a specific request.

This helps avoid unnecessary correlation across wallets and makes lifecycle controls easier to scope. Reusing a single long-lived identical bundle across multiple unrelated wallets can expand tracking, compromise, and revocation impact.

Record the bundle identifier, requesting wallet context, issuance date, and applicable status information needed to distinguish one issued bundle from another.

## Multiple CSPs

A wallet can hold attribute bundles from multiple CSPs, and one federation assertion can carry multiple bundles where the federation profile allows it.

The RP should evaluate each bundle according to its own issuer, signature, trust agreement, attribute authority, and validity status. A trusted bundle from one CSP does not automatically make another CSP's bundle acceptable.

When attributes from multiple CSPs conflict, define how the RP handles inconsistency rather than silently choosing whichever value is most convenient.

## Attribute scope and derived values

Bundles can contain direct subscriber attributes or derived attribute values.

Use the minimum attribute scope needed for the relying-party purpose. Where a yes/no, threshold, category, or other derived result satisfies the use case, avoid disclosing a more detailed source attribute merely because it is available.

Examples of governance questions include:

- Does the RP need a date of birth, or only an age-over-threshold result?
- Does the RP need a full address, or only a region or residency result?
- Is the requested attribute necessary for the transaction purpose?
- Is the CSP authoritative or sufficiently credible for that attribute?
- Is the wallet permitted by the trust agreement to release it?

## Selective disclosure

Attribute-bundle technology may support selective disclosure so a wallet can reveal only part of a signed attribute set while preserving CSP-verifiable integrity.

Where selective disclosure is available, design the RP request so it asks only for data needed for the transaction. Do not use technical ability to request more information as the default business requirement.

Subscriber-controlled wallet flows should present understandable runtime information about what the RP is requesting and why, consistent with the federation privacy requirements.

## Validity periods

NIST recommends limiting the period during which an issued attribute bundle remains valid.

Validity duration should reflect factors such as:

- how frequently the underlying attribute can change;
- harm from continued use of stale information;
- availability of real-time or privacy-preserving status checks;
- subscriber-account lifecycle;
- fraud and compromise risk; and
- operational ability to reissue bundles.

A long cryptographic validity period should not be used to avoid implementing appropriate lifecycle management.

## Invalidation

SP 800-63C-4 requires CSPs that issue attribute bundles to provide a way to invalidate them.

Invalidation can become necessary after:

- subscriber-account termination;
- detected compromise;
- fraudulent issuance;
- correction of material attribute information;
- loss of authorization for the wallet;
- key compromise;
- administrative revocation; or
- another event defined by the federation trust agreement.

The CSP should be able to identify which bundles are affected and communicate invalid status through the supported mechanism.

## Privacy-preserving status checks

Where the federation ecosystem uses a status service, NIST recommends a privacy-preserving design that does not alert the CSP every time a particular subscriber uses a bundle at a specific RP.

A status mechanism should therefore be evaluated for correlation risk as well as security value.

Questions include:

- Does the CSP learn which RP is checking the bundle?
- Does a unique status endpoint identify the subscriber?
- Can cached or batch status data reduce transaction-level tracking?
- Does the design expose unnecessary RP, wallet, or subscriber identifiers?
- Can the RP determine revocation status without giving the issuer a complete usage history?

## RP verification

Before relying on an attribute bundle, the RP should verify at least the properties required by the applicable federation profile and trust agreement.

A reusable verification sequence includes:

1. identify the CSP that issued the bundle;
2. obtain the correct CSP verification key through the trusted discovery or registration process;
3. validate the CSP signature;
4. verify that the bundle is bound to the expected wallet or key when the profile requires such binding;
5. check validity times;
6. check invalidation or status information where required;
7. confirm that the requested attribute is within the CSP's trusted authority and the RP's allowed purpose; and
8. separately validate the surrounding wallet or IdP assertion.

Fail closed when critical issuer, signature, binding, validity, or status checks cannot be completed.

## Key rotation and discovery

CSP signing-key rotation must not leave RPs unable to validate still-valid bundles or, conversely, cause expired keys to remain trusted indefinitely.

Define:

- how verification keys are published or distributed;
- how key identifiers map to issued bundles;
- overlap periods during rotation;
- how compromised keys are revoked;
- how RPs refresh cached verification data; and
- how historical verification is handled if audit requirements require it.

The method may use CSP-controlled discovery, federation-authority metadata, manual configuration, or another trusted mechanism defined by the ecosystem.

## Subscriber and wallet lifecycle

Bundle lifecycle should follow relevant account and wallet events.

Examples include:

- new wallet enrollment;
- wallet replacement;
- device loss;
- wallet signing-key rotation;
- subscriber attribute correction;
- subscriber-account suspension or termination;
- migration to another wallet provider; and
- recovery after compromise.

Do not assume that deleting a wallet app automatically invalidates bundles previously issued to that wallet.

## Evidence to retain

Where appropriate, retain:

- bundle identifier;
- issuer/CSP;
- requesting wallet identifier or verification key;
- issuance time;
- included attribute classes;
- applicable validity period;
- status or invalidation state;
- CSP signing-key identifier;
- issuance-policy version;
- invalidation reason and time where applicable; and
- the NIST/profile version used for the design review.

Retention should be limited by privacy, legal, audit, and security needs rather than keeping every federation artifact indefinitely.

## Failure handling

Define RP behavior for:

- expired bundles;
- unknown issuers;
- unverifiable signatures;
- revoked or invalidated bundles;
- stale status information;
- missing wallet binding;
- conflicting attributes from multiple CSPs; and
- unavailable discovery/status infrastructure.

A degraded federation dependency should not silently convert a verified attribute into an unverified self-asserted claim.

## Sources

- NIST SP 800-63C-4 — Federation and Assertions: https://pages.nist.gov/800-63-4/sp800-63c.html
- NIST SP 800-63 Revision 4 publication hub: https://pages.nist.gov/800-63-4/

## Scope note

This article summarizes reusable attribute-bundle lifecycle and verification considerations from NIST SP 800-63C-4. It does not claim that any credential, wallet, identity provider, relying party, or ORCHORDS system implements NIST-conformant attribute bundles or achieves a particular Federation Assurance Level.