---
title: NIST SP 800-63C Federation and Assertions Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST SP 800-63C Rev. 3 (June 2017, errata 2020) — Digital Identity Guidelines — Federation and Assertions; https://pages.nist.gov/800-63-3/sp800-63c.html
---

# NIST SP 800-63C Federation and Assertions Governance

## Scope

This card governs how `orchords-docs` evaluates federation and assertions against NIST SP 800-63C. It is the reference input for any KB card that touches SAML, OIDC, federated identity providers, or assertion security.

## Why this card exists

NIST SP 800-63C defines the canonical federal guidance for federated identity, assertions, and relying parties. Without an explicit card, the KB cites federation practices that do not align with the three federation assurance levels (FAL).

## Document set

- **NIST SP 800-63C** (June 2017, errata 2020) — Federation and Assertions.
- **NIST SP 800-63B** — Authentication.
- **NIST SP 800-63A** — Enrollment and Identity Proofing.

References: `https://pages.nist.gov/800-63-3/sp800-63c.html`.

## Federation assurance levels (FAL)

| FAL | Description |
|---|---|
| FAL1 | bearer assertion (no cryptographic binding) |
| FAL2 | cryptographic binding (JWT signed assertion, holder-of-key) |
| FAL3 | cryptographic binding + strongly bound assertion (mTLS, holder-of-key, audience restriction) |

References: SP 800-63C § 4.

## Assertion types

| Type | Use |
|---|---|
| SAML 2.0 | XML-based |
| JWT | JSON-based |
| OIDC ID Token | OIDC-flavored JWT |
| Custom JSON | custom JSON Web Token |

## Subscriber, identity provider, relying party

| Role | Description |
|---|---|
| Subscriber | end user |
| IdP (identity provider) | issues assertion |
| RP (relying party) | consumes assertion |
| CSP (credential service provider) | issues credentials |

## Pseudonymous identifiers

SP 800-63C § 5.1.1:

- Use `pairwise` / `pairwise_identifier` for privacy.
- Use `public` for non-private.
- Never share a private identifier across RPs.

## Cross-reference

| Domain | Card |
|---|---|
| SAML | `SAML_2_0_VERSION_GOVERNANCE.md` |
| OIDC | `OIDC_VERSION_GOVERNANCE.md` |
| OAuth | `OAUTH_2_1_VERSION_GOVERNANCE.md` |
| 800-63B | `NIST_SP_800_63B_IA_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card that touches federation.
2. Confirm the FAL is identified.
3. Confirm the assertion type is identified.
4. Update the next-review date.

## Sources

- NIST SP 800-63C: `https://pages.nist.gov/800-63-3/sp800-63c.html`
- NIST SP 800-63-3: `https://pages.nist.gov/800-63-3/`
- NIST SP 800-63A: `https://pages.nist.gov/800-63-3/sp800-63a.html`
