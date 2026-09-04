# Network Management Plane Isolation Review Template

Use this record to review how network-device management traffic is separated from production/customer/data-plane traffic. Keep real addresses, credentials, routing details, and sensitive topology in protected evidence rather than this public template.

## Review metadata

- Network/device class: `<class>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Management architecture: `<out-of-band / management VRF / dedicated zone / other>`
- Evidence location: `<protected reference>`

## Management-path inventory

| Management service | Approved source class | Dedicated management path? | Internet reachable? | Default-deny policy? | Egress restricted? | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| `<SSH/HTTPS/SNMP/AAA/etc.>` | `<admin workstation/jump host/etc.>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<yes/no>` | `<reference>` |

## Isolation checks

- [ ] Device management is not performed directly from the public internet.
- [ ] Management traffic is restricted to a dedicated out-of-band network, management VRF, or other enforced management zone appropriate to the architecture.
- [ ] Production/customer/data-plane address space cannot directly initiate management sessions unless explicitly required and approved.
- [ ] Lateral management paths between managed devices are restricted where they are not required.
- [ ] Management-plane ACLs or equivalent policy enforcement use an allowlisted/default-deny model.
- [ ] Management-plane egress is limited to explicitly required services such as approved AAA, logging, flow, or telemetry collectors.
- [ ] Dedicated administrative workstations or approved jump systems are used where required by the design.
- [ ] IPv4 and IPv6 management reachability are both reviewed where enabled.
- [ ] Control-plane rate limiting or equivalent protection is reviewed where supported and appropriate.

## Verification evidence

- Source-to-management reachability test: `<reference/result>`
- Data-plane-to-management negative test: `<reference/result>`
- Internet-to-management negative test: `<reference/result>`
- Management-egress test: `<reference/result>`
- ACL/policy review: `<reference/result>`

## Findings and actions

- Findings: `<text>`
- Required changes: `<text>`
- Owner/date: `<owner / YYYY-MM-DD>`
- Retest result: `<result>`

## Sources

- CISA, Enhanced Visibility and Hardening Guidance for Communications Infrastructure: https://www.cisa.gov/resources-tools/resources/enhanced-visibility-and-hardening-guidance-communications-infrastructure
- CISA Joint Cybersecurity Advisory AA25-239A, Countering Chinese State-Sponsored Actors Compromise of Networks Worldwide to Feed Global Espionage System: https://www.cisa.gov/news-events/cybersecurity-advisories/aa25-239a
