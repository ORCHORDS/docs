# Network Management Protocol, AAA, and Logging Review Template

Use this record to review administrative protocols, centralized authentication/authorization/accounting, and protected management logging for network infrastructure. Never place actual credentials, community strings, keys, addresses, or sensitive configuration values in this public template.

## Review metadata

- Device/network class: `<class>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Central AAA system class: `<TACACS+/RADIUS/other>`
- Central logging system class: `<syslog/SIEM/other>`

## Management services

| Protocol/service | Enabled? | Encrypted/authenticated? | Restricted by ACL/policy? | Central AAA? | Central logging? | Required? | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `<SSH/HTTPS/SNMPv3/SCP/SFTP/etc.>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<yes/no/n-a>` | `<yes/no>` | `<yes/no>` | `<reference>` |

## Review checks

- [ ] Unencrypted or unauthenticated management protocols such as Telnet, FTP, or plaintext HTTP are disabled unless a documented exceptional constraint exists.
- [ ] Administrative access uses encrypted and authenticated protocols such as SSH, HTTPS, SFTP/SCP, or another approved secure protocol.
- [ ] SNMP, if required, uses an authenticated/encrypted configuration such as SNMPv3 with access restrictions appropriate to the platform.
- [ ] Administrative protocols are allowlisted to approved management stations, subnets, or jump systems.
- [ ] Central AAA is used for routine administration where supported, with emergency local accounts separately governed.
- [ ] Authentication, authorization, and accounting events are sent to protected centralized logging.
- [ ] Management log transport provides appropriate confidentiality, integrity, and authentication protections where supported.
- [ ] Unused discovery and management protocols/services are disabled or restricted to only the interfaces where required.
- [ ] Failed/denied management attempts are visible to monitoring and alerting.

## Verification evidence

- Protocol enumeration/scan: `<reference/result>`
- Negative test for disabled plaintext protocol: `<reference/result>`
- AAA authentication/accounting test: `<reference/result>`
- Central log receipt test: `<reference/result>`
- ACL/allowlist negative test: `<reference/result>`

## Findings and actions

- Weak/unneeded protocols: `<text>`
- AAA gaps: `<text>`
- Logging gaps: `<text>`
- Corrective actions/owner/date: `<text>`

## Sources

- CISA, Enhanced Visibility and Hardening Guidance for Communications Infrastructure: https://www.cisa.gov/resources-tools/resources/enhanced-visibility-and-hardening-guidance-communications-infrastructure
- CISA Joint Cybersecurity Advisory AA25-239A: https://www.cisa.gov/news-events/cybersecurity-advisories/aa25-239a
