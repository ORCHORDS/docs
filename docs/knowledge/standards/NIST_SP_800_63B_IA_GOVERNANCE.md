---
title: NIST SP 800-63B Digital Identity Guidelines — Authentication and Lifecycle Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST SP 800-63B Rev. 3 (June 2017, errata update 2020) — Digital Identity Guidelines — Authentication and Lifecycle; https://pages.nist.gov/800-63-3/sp800-63b.html
---

# NIST SP 800-63B Digital Identity Guidelines — Authentication and Lifecycle Governance

## Scope

This card governs how `orchords-docs` evaluates authentication assurance levels and identity lifecycle against NIST SP 800-63B Rev. 3. It is the reference input for any KB card that touches authenticators, password policy, MFA, or session management.

## Why this card exists

NIST SP 800-63B Rev. 3 (with 2020 errata) is the canonical US federal authentication guideline. Without an explicit card, the KB cites 800-63B practices that ignore the password complexity pivot (length over entropy rules) and the authenticator taxonomy.

## Document set

- **NIST SP 800-63B Rev. 3** (June 2017, errata 2020) — Authentication and Lifecycle.

References: `https://pages.nist.gov/800-63-3/sp800-63b.html`.

## Assurance levels

| AAL | Description |
|---|---|
| AAL1 | single-factor |
| AAL2 | two-factor (one replay-resistant) |
| AAL3 | hardware authenticator + verifier impersonation resistance |

## Authenticator types

| Type | AAL | Replay-resistant |
|---|---|---|
| Memorized secret (password) | AAL1 | n/a |
| Look-up secret | AAL1 | yes |
| Out-of-band device | AAL2 | yes |
| Single-factor OTP | AAL2 | yes |
| Multi-factor OTP | AAL2 | yes |
| Single-factor crypto | AAL2 | yes |
| Multi-factor crypto | AAL3 | yes |

## Password policy (per 800-63B 2020 errata)

| Rule | Recommendation |
|---|---|
| Minimum length | 8 (AAL1), 12+ recommended |
| Maximum length | 64 |
| Complexity rules | NOT REQUIRED |
| Periodic rotation | NOT REQUIRED |
| Hints | NOT PERMITTED |
| Knowledge-based auth | NOT PERMITTED |
| Composition rules | encouraged (longer passphrases) |

References: `https://pages.nist.gov/800-63-3/sp800-63b.html#-5111-memorized-secret-verifiers`.

## Session management

| Setting | Value |
|---|---|
| Reauthentication | at AAL2+ every 12h |
| Idle timeout | 30 min for AAL2 |
| Maximum session | 12 hours |
| Binding | to IP / device where feasible |

## Cross-reference

| Domain | Card |
|---|---|
| OAuth | `OAUTH_2_1_VERSION_GOVERNANCE.md` |
| OIDC | `OIDC_VERSION_GOVERNANCE.md` |
| SAML | `SAML_2_0_VERSION_GOVERNANCE.md` |
| 800-53 | `NIST_SP_800_53_R5_SECURITY_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every KB reference card that touches authentication.
2. Confirm the AAL is identified.
3. Update the next-review date.

## Sources

- NIST SP 800-63B: `https://pages.nist.gov/800-63-3/sp800-63b.html`
- NIST SP 800-63-3: `https://pages.nist.gov/800-63-3/`
- NIST SP 800-63A: `https://pages.nist.gov/800-63-3/sp800-63a.html`
- NIST SP 800-63C: `https://pages.nist.gov/800-63-3/sp800-63c.html`
