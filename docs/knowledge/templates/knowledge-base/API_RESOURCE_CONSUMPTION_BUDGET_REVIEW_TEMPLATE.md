# API Resource Consumption Budget Review Template

Use this record to review per-request, per-client, and paid-provider consumption limits using the risk dimensions described by OWASP API4:2023.

## Review metadata

- API/operation: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Traffic class: `<public/internal/partner or other non-sensitive class>`

## Per-request limits

| Dimension | Enforced limit | Enforcement layer | Test evidence |
| --- | --- | --- | --- |
| Execution time | `<value>` | `<layer>` | `<reference>` |
| Request/upload size | `<value>` | `<layer>` | `<reference>` |
| Response/page size | `<value>` | `<layer>` | `<reference>` |
| Batch cardinality | `<value>` | `<layer>` | `<reference>` |
| Query/operation complexity | `<value>` | `<layer>` | `<reference>` |
| Memory/process/platform budget | `<value>` | `<layer>` | `<reference>` |

## Interaction-frequency limits

- Per-client/user rate limit: `<value>`
- Per-tenant rate/quota: `<value>`
- Sensitive/expensive-operation quota: `<value>`
- Retry/deduplication control: `<summary>`

## Paid downstream services

| Provider/service class | Unit-cost driver | Application quota | Provider spending limit | Alert threshold |
| --- | --- | --- | --- | --- |
| `<service>` | `<request/size/duration/etc.>` | `<limit>` | `<limit or unavailable>` | `<threshold>` |

## Verification

- [ ] Maximum legal request shape remains within service capacity.
- [ ] Requests below the frequency limit cannot exhaust a separate resource dimension.
- [ ] Retry loops cannot create unbounded duplicate paid operations.
- [ ] Budget exhaustion is observable and handled explicitly.
- [ ] Billing alerts or hard provider limits are tested where feasible.

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`

## Source

- OWASP API4:2023 Unrestricted Resource Consumption: https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/
