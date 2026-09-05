# Syncable Authenticator Assurance Review Template

Use this record to assess syncable authenticators and passkeys against NIST SP 800-63B-4 assurance requirements. Keep vendor- or tenant-sensitive configuration details in protected evidence rather than this public template.

## Review metadata

- Service/application: `<name>`
- Authenticator technology: `<type/provider-neutral description>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Target NIST assurance level: `<AAL1/AAL2/AAL3>`

## Key and sync characteristics

| Property | Result | Evidence |
| --- | --- | --- |
| Private key exportable? | `<yes/no/unknown>` | `<reference>` |
| Credential sync enabled? | `<yes/no>` | `<reference>` |
| Sync fabric encrypts authenticator data? | `<result>` | `<reference>` |
| Access to sync fabric protected by appropriate authentication? | `<result>` | `<reference>` |
| Recovery path documented and tested? | `<result>` | `<reference>` |

## Assurance checks

- [ ] Syncable authenticators are not classified as NIST AAL3 authenticators.
- [ ] If the target is AAL3, the selected authenticator uses a non-exportable private key instead.
- [ ] For AAL2 use, sync-fabric protections and recovery behavior are included in the threat and assurance review.
- [ ] Phishing resistance is evaluated separately from key exportability/syncability.
- [ ] Product claims distinguish “passkey,” “phishing-resistant,” and “AAL3-capable” rather than treating them as synonyms.

## Verification

- Backup/export/sync behavior tested: `<result>`
- Key-storage architecture evidence: `<reference>`
- Sync-fabric access-control evidence: `<reference>`
- Target-AAL classification result: `<result>`

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Source

- NIST SP 800-63B-4, Syncable Authenticators and Authenticator Assurance Levels: https://pages.nist.gov/800-63-4/sp800-63b.html
