# API Object Authorization Review Template

Use this record to verify object-level authorization for API operations that accept client-controlled object identifiers. Keep examples generic and do not place real customer identifiers or sensitive production data in this record.

## Review metadata

- API/operation: `<name>`
- Resource/object type: `<type>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Caller roles/capabilities tested: `<roles>`

## Identifier surfaces

| Identifier location | Example shape | Operation(s) | Authorization rule |
| --- | --- | --- | --- |
| Path | `<resource-id>` | `<read/update/delete>` | `<rule>` |
| Query | `<filter or id>` | `<operation>` | `<rule>` |
| Header | `<header-carried id>` | `<operation>` | `<rule>` |
| Body | `<nested object id>` | `<operation>` | `<rule>` |

## Cross-identity test matrix

| Caller | Object owner/context | Action | Expected | Actual | Evidence |
| --- | --- | --- | --- | --- | --- |
| `<identity A>` | `<A-owned>` | `<read>` | `<allow>` | `<result>` | `<reference>` |
| `<identity A>` | `<B-owned>` | `<read>` | `<deny>` | `<result>` | `<reference>` |

## Review checks

- [ ] Every operation using a client-selected object performs an authorization decision after resolving the object.
- [ ] Authorization is evaluated separately for read, update, delete, export, and other exposed actions.
- [ ] Identifier unpredictability is treated only as defense in depth, not as the access-control decision.
- [ ] Nested or indirect object identifiers receive equivalent authorization checks.
- [ ] Unauthorized requests are rejected before sensitive response data or state changes occur.

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Sources

- OWASP API1:2023 Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- OWASP WSTG API Broken Object Level Authorization: https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/12-API_Testing/02-API_Broken_Object_Level_Authorization
