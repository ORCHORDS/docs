# NIST SP 800-63-3 Digital Identity Guidelines Version Governance

## Purpose

NIST SP 800-63-3, *Digital Identity Guidelines*, was published in June 2017 (with errata updates incorporated through March 2, 2020) and provides the umbrella framework for digital identity assurance used across U.S. federal agencies. The suite is structured into a base document and companion volumes:

- SP 800-63-3 — enrollment and identity-proofing assurance (IAL);
- SP 800-63A — enrollment and identity-proofing lifecycle details;
- SP 800-63B — authenticators and authentication lifecycle (AAL);
- SP 800-63C — federation and assertions.

Documents that assert digital identity assurance levels should cite the SP 800-63-3 base plus the relevant companion volume. A bare reference to "NIST digital identity" without naming the volume and the assurance level is incomplete.

## Current context and source status

SP 800-63-3 has been superseded by NIST SP 800-63-4 as of August 1, 2025. Until a migration is complete for a given system, SP 800-63-3 continues to apply. Documents that adopt SP 800-63-4 should reference SP 800-63-4, not SP 800-63-3, and should preserve test evidence that distinguishes the two baselines.

The IAL/AAL/FAL levels defined in SP 800-63-3 (IAL1/IAL2/IAL3 and AAL1/AAL2/AAL3) remain the most widely deployed labels in vendor and agency documentation. Where SP 800-63-4 renames or restructures these concepts, both labels should be crosswalked rather than collapsed.

## Governance pattern

1. Cite SP 800-63-3 plus the specific companion volume in scope (800-63A, 800-63B, or 800-63C) for each identity service or relying-party integration.
2. Assign a single, recorded IAL for identity-proofing, a single AAL for authentication, and a single FAL for federation assertions. Do not split a single transaction across multiple assurance levels without documenting the protocol-level binding.
3. Document the authenticator types, the number of factors, replay resistance, verifier-impersonation resistance, and the cryptographic mechanisms used. These map to AAL1, AAL2, and AAL3 requirements.
4. Record the identity-proofing process for each IAL, including the evidence accepted, the validation steps, the in-person or remote supervised session details, and the records produced.
5. For federated transactions, identify the assertion format (for example SAML, OAuth/OIDC with defined profile) and bind it to the FAL.
6. Maintain a documented migration plan to SP 800-63-4 where the agency or product has announced adoption of the new baseline.
7. Treat authenticator compromise as a documented event with re-issuance, revocation, and audit-trail expectations.
8. Apply privacy controls (for example, minimization of personal data in assertions and retention limits) consistent with the volume in force.

## Validation and evidence

Identity assurance evidence includes:

- the IAL/AAL/FAL assignment and the basis for each;
- identity-proofing records with evidence type, validation steps, and session metadata;
- authenticator inventory and binding records;
- federation-trust agreements and assertion-format specifications;
- test evidence that the protocol-level binding matches the documented AAL/FAL;
- privacy and retention controls applied to the collected identity data;
- migration status to SP 800-63-4 if applicable.

## Failure correction

The most common defects are:

- An AAL label applied without the corresponding authenticator requirements, such as claiming AAL3 without a hardware-based authenticator with verifier-impersonation resistance.
- Identity proofing labeled IAL2 or IAL3 without recording the evidence type, validation, or supervised-session details.
- Federation assertions that bind a high FAL but the underlying authentication used a lower AAL.
- Documentation that mixes SP 800-63-3 and SP 800-63-4 terms without distinguishing the baseline.

Corrective actions include re-issuing the assurance assignment, replacing or re-binding the authenticator, and re-running the federation assertions to ensure the protocol-level binding matches the assurance label.

## Limitations

SP 800-63-3 does not define:

- specific identity-proofing services (it constrains them);
- specific assertion protocol profiles beyond a high-level framework;
- machine-to-machine authentication outside the human-identity model.

The publication also defers to FIPS 140-validated cryptographic modules for the cryptographic operations it requires.

## Migration to SP 800-63-4

SP 800-63-4 (published July 31, 2025) is the current NIST Digital Identity Guidelines. SP 800-63-3 has been formally superseded as of August 1, 2025. A profile that has begun SP 800-63-4 adoption should:

- identify the components of SP 800-63-4 it is adopting (the SP 800-63-4 set is structured similarly but may rename or restructure concepts);
- record the SP 800-63-3 components that are being deprecated or replaced;
- maintain test evidence that distinguishes the SP 800-63-3 and SP 800-63-4 baselines during a transition window;
- update agency and supplier documentation to reference SP 800-63-4 explicitly rather than SP 800-63-3 once the transition is complete.

A profile that cites SP 800-63-3 after SP 800-63-4 has been formally adopted is not necessarily incorrect, but should record the rationale (for example, "this contract was signed before SP 800-63-4 adoption and is bound to SP 800-63-3 evidence").

## Federation profile guidance

For federated transactions, SP 800-63C specifies the federation assurance level (FAL) and the assertion format constraints. Profiles that integrate with SAML 2.0, OpenID Connect, or other federation protocols should bind the assertion format to the FAL and should record the trust framework under which the assertion is accepted. Privacy considerations (data minimization, audience restriction, and token lifetime) should be cross-referenced with NIST SP 800-63C and with the privacy control overlays applicable to the data exchanged in the assertion.

## Privacy and retention considerations

SP 800-63-3 limits the personally identifiable information collected during identity proofing to what is necessary for the claimed IAL, and it requires retention policies that are reasonable and documented. Profiles should record:

- the data elements collected at each IAL;
- the retention period for each element;
- the destruction event for each element;
- the legal authority for collection and retention;
- the privacy notice given to the subscriber.

Profiles that claim IAL2 or IAL3 should also document the supervised-session evidence and the chain of custody for the evidence collected.

## Canonical sources

- NIST SP 800-63-3 base document (NIST pages): https://pages.nist.gov/800-63-3/sp800-63-3.html
- NIST SP 800-63B *Authentication and Lifecycle Management* (NIST pages): https://pages.nist.gov/800-63-3/sp800-63b.html
- NIST SP 800-63-4 publication page (NIST CSRC): https://csrc.nist.gov/pubs/sp/800/63/4/final

Sources were verified on September 1, 2026.
