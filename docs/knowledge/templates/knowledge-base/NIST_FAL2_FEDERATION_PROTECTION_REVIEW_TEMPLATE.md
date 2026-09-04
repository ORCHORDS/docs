# NIST FAL2 Federation Protection Review Template

Use this record to assess a federation transaction against NIST SP 800-63C-4 FAL2. This template captures NIST assurance evidence; it does not make FAL2 a universal requirement for systems outside that framework.

## Review metadata

- Federation connection: `<IdP to RP description>`
- Protocol/profile: `<OIDC/SAML/other>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Target federation assurance level: `<FAL2>`

## Transaction and assertion controls

| Control | Implementation | Test evidence | Result |
| --- | --- | --- | --- |
| Transaction initiated by RP | `<mechanism>` | `<reference>` | `<pass/fail>` |
| Assertion-injection protection | `<mechanism>` | `<reference>` | `<pass/fail>` |
| Single-RP audience restriction | `<mechanism>` | `<reference>` | `<pass/fail>` |
| Replay protection at RP | `<mechanism>` | `<reference>` | `<pass/fail>` |
| RP transaction nonce/binding where required | `<mechanism>` | `<reference>` | `<pass/fail>` |
| Federated identifier contains no plaintext PII | `<mechanism>` | `<reference>` | `<pass/fail>` |

## Review checks

- [ ] Unsolicited IdP-initiated assertion delivery cannot create an FAL2 RP session.
- [ ] Assertions received outside the expected stage of an RP-initiated transaction are rejected.
- [ ] An assertion issued for one RP cannot be accepted by another RP.
- [ ] Reusing a captured assertion does not create a second authenticated session contrary to the protocol replay model.
- [ ] Required request nonce or transaction-binding values are verified before session creation.
- [ ] Federated identifiers do not contain usernames, email addresses, employee numbers, or other plaintext personal information at FAL2.
- [ ] Internal documentation references SP 800-63C-4 rather than superseded Revision 3 FAL2 assumptions.

## Adversarial test evidence

- Unsolicited assertion test: `<result/reference>`
- Wrong-audience test: `<result/reference>`
- Replay test: `<result/reference>`
- Missing/mismatched transaction-binding value test: `<result/reference>`
- Identifier privacy inspection: `<result/reference>`

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Source

- NIST SP 800-63C-4, final federation requirements: https://pages.nist.gov/800-63-4/sp800-63c.html
