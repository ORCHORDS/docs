# NIST FAL3 Holder-of-Key and Bound-Authenticator Review Template

Use this record to assess the subscriber-proof portion of NIST SP 800-63C-4 FAL3. Record architecture and test evidence without exposing private keys, real subscriber identifiers, or production secrets.

## Review metadata

- Federation connection: `<IdP to RP description>`
- Protocol/profile: `<protocol>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- FAL3 proof model: `<holder-of-key/bound authenticator>`

## Assertion evidence

- Assertion validates successfully: `<pass/fail>`
- Assertion indicates the intended FAL3/bound-authenticator context: `<evidence>`
- Authenticator identifier carried or referenced by assertion when applicable: `<non-sensitive description>`
- RP subscriber-account resolution mechanism: `<summary>`

## Authenticator evidence

| Requirement | Result | Evidence |
| --- | --- | --- |
| Subscriber proves possession directly to RP | `<pass/fail>` | `<reference>` |
| Authenticator resolves to correct RP subscriber account | `<pass/fail>` | `<reference>` |
| Holder-of-key authenticator is phishing-resistant | `<pass/fail/not applicable>` | `<reference>` |
| Bound-authenticator proof is separately validated from assertion | `<pass/fail/not applicable>` | `<reference>` |
| Failed authenticator proof prevents session creation | `<pass/fail>` | `<reference>` |

## Review checks

- [ ] A valid bearer assertion alone cannot create an FAL3 session.
- [ ] The RP validates the assertion and the subscriber authenticator proof as separate required conditions.
- [ ] Holder-of-key assertions reference an authenticator the subscriber can prove possession of at the RP.
- [ ] Holder-of-key authenticators satisfy NIST phishing-resistance requirements.
- [ ] Bound-authenticator identifiers are stored and associated with the correct RP subscriber account.
- [ ] An incorrect, missing, removed, or unbound authenticator causes an RP error and no authenticated FAL3 session.

## Verification scenarios

| Scenario | Expected | Actual | Evidence |
| --- | --- | --- | --- |
| Valid assertion + valid authenticator proof | `<session created>` | `<result>` | `<reference>` |
| Valid assertion + no authenticator proof | `<deny>` | `<result>` | `<reference>` |
| Valid assertion + wrong authenticator | `<deny>` | `<result>` | `<reference>` |
| Valid assertion + removed/unbound authenticator | `<deny>` | `<result>` | `<reference>` |

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Source

- NIST SP 800-63C-4, FAL3, Holder-of-Key Assertions, and Bound Authenticators: https://pages.nist.gov/800-63-4/sp800-63c.html
