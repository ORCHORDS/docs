# API Property Authorization Review Template

Use this record to assess read and write authorization at the object-property level, including excessive exposure and mass-assignment risks described by OWASP API3:2023.

## Review metadata

- API/operation: `<name>`
- Object/resource type: `<type>`
- Caller roles/capabilities reviewed: `<roles>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`

## Read-property review

| Property | Returned to whom? | Authorization rule | Required by contract? | Test evidence |
| --- | --- | --- | --- | --- |
| `<property>` | `<caller>` | `<rule>` | `<yes/no>` | `<reference>` |

- [ ] Response construction explicitly selects allowed properties.
- [ ] Persistence/domain objects are not generically serialized into public responses.
- [ ] Response schema validation enforces the intended field set.

## Write-property review

| Property | Writable by whom? | Authorization rule | Input-schema field? | Test evidence |
| --- | --- | --- | --- | --- |
| `<property>` | `<caller>` | `<rule>` | `<yes/no>` | `<reference>` |

- [ ] Input models allowlist mutable properties.
- [ ] Unknown-field behavior is defined and tested.
- [ ] Sensitive state transitions receive explicit authorization checks.
- [ ] Adding an internal persistence property does not automatically make it API-writable.

## Findings

- Sensitive exposure findings: `<text>`
- Unauthorized mutation findings: `<text>`
- Corrective actions/owner/date: `<text>`

## Source

- OWASP API3:2023 Broken Object Property Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/
