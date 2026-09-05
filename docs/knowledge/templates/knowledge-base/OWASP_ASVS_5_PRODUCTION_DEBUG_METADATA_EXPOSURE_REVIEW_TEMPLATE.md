# OWASP ASVS 5.0 Production Debug and Source-Metadata Exposure Review Template

Use this record to review production deployment exposure against OWASP ASVS 5.0.0 requirements V13.4.1 and V13.4.2. Keep actual internal paths, secrets, production hostnames, and sensitive diagnostic output in protected evidence rather than this public template.

## Review metadata

- Application/deployment class: `<scope>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Production build/deployment reference: `<reference>`
- Components reviewed: `<web/app/runtime/framework/proxy/other>`

## Component review

| Component | Debug/development mode expected | Actual state | Source-control metadata present? | Externally reachable? | App-process reachable? | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `<component>` | `<disabled>` | `<state>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<reference>` |

## Review checks

- [ ] Production deployment artifacts do not contain `.git`, `.svn`, or other source-control metadata, **or** those folders are inaccessible both externally and to the application itself. *(ASVS V13.4.1)*
- [ ] Debug modes are disabled for all production components. *(ASVS V13.4.2)*
- [ ] Framework/runtime development consoles, interactive exception pages, debug endpoints, and hot-reload/development servers are not enabled in production.
- [ ] Production configuration is checked at the deployed runtime level rather than inferred only from source/build configuration.
- [ ] A deployment/package inspection verifies that excluded metadata does not reappear through copied workspace directories or container/image layers accessible to the running application.
- [ ] Representative error paths do not expose debug-mode output or internal diagnostic detail to an external client.
- [ ] Configuration drift or deployment changes that re-enable debug behavior are detectable through the organization's configuration/deployment controls.

## Verification evidence

- Production artifact/image/package inspection: `<reference/result>`
- External source-metadata reachability test: `<reference/result>`
- Application-process source-metadata access test: `<reference/result>`
- Debug/development endpoint test: `<reference/result>`
- Representative exception/error response: `<reference/result>`
- Runtime configuration evidence: `<reference/result>`

## Findings and actions

- Source-control metadata findings: `<text>`
- Debug/development mode findings: `<text>`
- Runtime/deployment drift findings: `<text>`
- Corrective actions/owner/date: `<text>`

## Source basis

- OWASP ASVS 5.0.0 requirements V13.4.1 and V13.4.2: https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv
- OWASP ASVS project: https://owasp.org/www-project-application-security-verification-standard/
