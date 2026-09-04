# NIST AAL3 Authenticator and Session Review Template

Use this record when assessing a service against NIST SP 800-63B-4 AAL3. Record evidence for authenticator properties and session reauthentication together because both contribute to the assurance claim.

## Review metadata

- Service/application: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Authenticator type: `<description>`
- Session implementation: `<browser/native/API or other>`

## Authenticator assurance evidence

| Requirement area | Result | Evidence |
| --- | --- | --- |
| Private key non-exportable | `<pass/fail>` | `<reference>` |
| Hardware-backed or isolated key protection | `<pass/fail>` | `<reference>` |
| Phishing resistance | `<pass/fail>` | `<reference>` |
| Replay resistance | `<pass/fail>` | `<reference>` |
| Authentication intent | `<pass/fail>` | `<reference>` |

## Session and reauthentication evidence

- Configured overall reauthentication timeout: `<duration>`
- Configured inactivity timeout: `<duration>`
- Reauthentication authenticator path: `<description>`
- Reauthentication retains AAL3 requirements: `<pass/fail>`

## Review checks

- [ ] The private authentication key is non-exportable.
- [ ] Key protection matches the NIST AAL3 hardware/isolation expectations applicable to the authenticator design.
- [ ] Authentication and reauthentication provide phishing resistance and replay resistance.
- [ ] At least one authenticator demonstrates authentication intent during initial authentication and reauthentication.
- [ ] Overall reauthentication timeout is no more than 12 hours.
- [ ] Inactivity timeout is configured at or below the NIST-recommended 15 minutes, or a deviation is explicitly documented and reviewed.
- [ ] Reauthentication does not silently fall back to a weaker assurance path while continuing to label the session AAL3.

## Verification evidence

- Key export/backup test: `<result>`
- Phishing/replay test: `<result>`
- Authentication-intent test: `<result>`
- Overall-timeout test: `<result>`
- Inactivity-timeout test: `<result>`
- Reauthentication end-to-end test: `<result>`

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Source

- NIST SP 800-63B-4, AAL3 and Reauthentication Requirements: https://pages.nist.gov/800-63-4/sp800-63b.html
