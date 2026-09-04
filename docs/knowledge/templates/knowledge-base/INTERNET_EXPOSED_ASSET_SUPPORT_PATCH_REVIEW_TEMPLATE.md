# Internet-Exposed Asset Support and Patch Review Template

Use this record to review the software-support, patching, and replacement state of assets that must remain internet-accessible. Do not place real addresses, credentials, sensitive topology, or exploit details in the public record.

## Review metadata

- Review scope: `<environment/service class>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Exposure inventory reference: `<reference>`

## Asset lifecycle and patch state

| Asset/service class | Internet exposure required? | Product/version | Supported by supplier? | Latest applicable security update assessed? | Current patch state | Replacement required? | Owner | Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `<asset>` | `<yes/no>` | `<version>` | `<yes/no/unknown>` | `<yes/no>` | `<current/gap/unknown>` | `<yes/no>` | `<role/team>` | `<reference>` |

## Review checks

- [ ] Supplier support status is verified from an authoritative source rather than inferred from installation age.
- [ ] Applicable security updates are identified and compared with the deployed version.
- [ ] Unsupported or end-of-life internet-exposed software/devices have a replacement or exposure-removal plan.
- [ ] Patch gaps on retained exposed assets have an owner, priority, and target date.
- [ ] Compensating controls do not become a permanent substitute for replacing unsupported technology without an explicit risk decision.
- [ ] Default credentials are changed or eliminated on assets that remain exposed.
- [ ] Remaining exposed assets use appropriate restricted-access, monitoring, and MFA controls where applicable.
- [ ] The review is repeated after material version, support-status, or exposure changes.

## Unsupported/EOL decision record

- Asset/service: `<name or class>`
- Support ended / ends: `<date or authoritative reference>`
- Public exposure still required?: `<yes/no + reason>`
- Immediate exposure reduction: `<action>`
- Replacement/upgrade plan: `<action + target date>`
- Temporary compensating controls: `<controls>`
- Risk/exception owner: `<role/team>`
- Exception expiry/review date: `<YYYY-MM-DD>`

## Evidence and actions

- Supplier lifecycle evidence: `<reference>`
- Patch/update evidence: `<reference>`
- External exposure verification: `<reference>`
- Remediation/replacement evidence: `<reference>`
- Retest result: `<result>`

## Source

- CISA, Internet Exposure Reduction Guidance, published June 4, 2025: https://www.cisa.gov/resources-tools/resources/exposure-reduction
