# Internet Exposure Inventory and Necessity Review Template

Use this record to identify internet-accessible assets, document why exposure is necessary, and record the decision to remove, restrict, or retain that exposure. Keep real IP addresses, internal hostnames, credentials, and sensitive topology in protected evidence rather than this public template.

## Review metadata

- Review scope: `<environment or service class>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Discovery sources used: `<scanner / DNS / cloud inventory / gateway / other>`
- Previous review reference: `<reference or none>`

## Exposure inventory

| Asset/service class | Internet reachable? | Discovery source | Business/operational need | Owner | Interdependencies reviewed? | Decision | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `<asset or service>` | `<yes/no>` | `<source>` | `<reason or none>` | `<role/team>` | `<yes/no>` | `<remove/restrict/retain>` | `<reference>` |

## Necessity review

For every retained exposure, record:

- Required external users/systems: `<description>`
- Required protocol/service: `<description>`
- Why private access, VPN, proxy, gateway, or another restricted path is insufficient: `<reason>`
- Expected operational impact if exposure is removed or restricted: `<impact>`
- Dependencies checked before change: `<reference>`
- Approval/decision owner: `<role or team>`
- Next reassessment date: `<YYYY-MM-DD>`

## Review checks

- [ ] Exposure was discovered independently rather than relying only on the documented inventory.
- [ ] Every discovered internet-accessible asset has an accountable owner.
- [ ] Every retained exposure has a current operational or business justification.
- [ ] Assets without a valid need for public reachability are removed from the internet or access is restricted.
- [ ] Interdependencies are reviewed before exposure changes to avoid unintended service disruption.
- [ ] Newly discovered or changed exposure is included in the routine assessment process.
- [ ] The review covers remote-access technologies and nontraditional connected assets where applicable.

## Actions and evidence

- Exposures removed: `<references>`
- Exposures restricted: `<references>`
- Exposures retained with justification: `<references>`
- Unknown/unowned exposures escalated: `<references>`
- Follow-up owner/date: `<owner / YYYY-MM-DD>`

## Sources

- CISA, Internet Exposure Reduction Guidance, published June 4, 2025: https://www.cisa.gov/resources-tools/resources/exposure-reduction
- CISA BOD 23-02 background on internet-exposed management interfaces: https://www.cisa.gov/news-events/alerts/2023/06/13/cisa-issues-bod-23-02-mitigating-risk-internet-exposed-management-interfaces
