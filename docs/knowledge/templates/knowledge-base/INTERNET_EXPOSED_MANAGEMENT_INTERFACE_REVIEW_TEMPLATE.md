# Internet-Exposed Management Interface Review Template

Use this record to review administrative or device-management interfaces that may be reachable from the public internet. CISA BOD 23-02 is binding on covered Federal Civilian Executive Branch agencies; outside that scope, this template uses the same risk-reduction concepts as voluntary security guidance and does not create a legal obligation.

## Review metadata

- System/service class: `<name or class>`
- Management function: `<administration / monitoring / configuration / other>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Exposure discovery source: `<source>`

## Management-interface inventory

| Interface/protocol | Internet reachable? | Public exposure required? | Restricted path / policy enforcement point | MFA | Monitoring | Patch/support state | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `<interface>` | `<yes/no>` | `<yes/no + reason>` | `<jump host/VPN/ZT/other>` | `<status>` | `<status>` | `<status>` | `<remove/restrict/retain>` |

## Review checks

- [ ] Each management interface was tested for actual internet reachability.
- [ ] Public exposure is removed when direct internet access is not operationally necessary.
- [ ] If remote administration is required, access is routed through a controlled and monitored path appropriate to the environment.
- [ ] A policy enforcement point, jump host, VPN, or equivalent control is separate from the management interface where the architecture calls for it.
- [ ] MFA is applied to remote administrative access where supported and appropriate.
- [ ] Ingress and egress activity for the exposed administrative path is monitored for anomalous behavior.
- [ ] Only required protocols and ports remain exposed.
- [ ] Management software/firmware is supported and current on applicable security updates.
- [ ] IPv4 and IPv6 exposure are both considered where either protocol is enabled.

## Verification evidence

- External reachability test: `<reference/result>`
- Restricted-access-path test: `<reference/result>`
- MFA test: `<reference/result>`
- Port/protocol scan: `<reference/result>`
- Monitoring/alert test: `<reference/result>`
- Patch/support verification: `<reference/result>`

## Findings and actions

- Findings: `<text>`
- Exposure removed/restricted: `<reference>`
- Exceptions with owner and expiry: `<reference>`
- Retest result: `<result>`

## Sources

- CISA, Internet Exposure Reduction Guidance, published June 4, 2025: https://www.cisa.gov/resources-tools/resources/exposure-reduction
- CISA, BOD 23-02: Mitigating the Risk from Internet-Exposed Management Interfaces: https://www.cisa.gov/news-events/alerts/2023/06/13/cisa-issues-bod-23-02-mitigating-risk-internet-exposed-management-interfaces
