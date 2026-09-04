# OWASP ASVS 5.0 Archive Extraction Safety Review Template

Use this record to review compressed-file and archive handling against OWASP ASVS 5.0.0 requirements V5.1.1, V5.2.3, and V5.2.5. This template operationalizes the requirements for evidence collection; it does not imply OWASP certification.

## Review metadata

- Application/upload feature: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Accepted archive/file formats: `<formats>`
- Extraction/processing library or service: `<implementation class>`

## Documented limits

| Control | Documented value/policy | Enforced before extraction? | Test evidence |
| --- | --- | --- | --- |
| Maximum uploaded size | `<value>` | `<yes/no>` | `<reference>` |
| Maximum uncompressed size | `<value>` | `<yes/no>` | `<reference>` |
| Maximum files/entries per archive | `<value>` | `<yes/no>` | `<reference>` |
| Permitted archive/file types | `<types>` | `<yes/no>` | `<reference>` |
| Symlink handling | `<reject / controlled allowlist / n-a>` | `<yes/no>` | `<reference>` |

## Review checks

- [ ] Each upload feature documents permitted file types/extensions and maximum size, including unpacked size where archives are supported. *(ASVS V5.1.1)*
- [ ] Compressed files are checked against the maximum allowed uncompressed size **before** extraction. *(ASVS V5.2.3)*
- [ ] The application checks the maximum number of archive entries before extraction. *(ASVS V5.2.3)*
- [ ] Archive limits are applied recursively or otherwise account for nested archive behavior according to the application design.
- [ ] Uploaded compressed files containing symlinks are rejected unless symlink support is specifically required. *(ASVS V5.2.5)*
- [ ] If symlinks are required, permitted targets are constrained by an explicit allowlist and cannot escape the intended extraction boundary. *(ASVS V5.2.5)*
- [ ] Rejected archives fail without leaving partially trusted extracted content available to later processing.
- [ ] Temporary extraction files and directories are cleaned up according to the application's storage lifecycle.

## Verification exercise

- Oversized uncompressed archive: `<reference/result>`
- Excessive-entry-count archive: `<reference/result>`
- Nested archive case: `<reference/result>`
- Symlink-containing archive: `<reference/result>`
- Allowed archive happy path: `<reference/result>`
- Partial-extraction cleanup check: `<reference/result>`

## Findings and actions

- Missing or unenforced limits: `<text>`
- Symlink/path findings: `<text>`
- Cleanup/state findings: `<text>`
- Corrective actions/owner/date: `<text>`

## Source basis

- OWASP ASVS 5.0.0 requirements V5.1.1, V5.2.3, V5.2.5: https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv
- OWASP ASVS project: https://owasp.org/www-project-application-security-verification-standard/
