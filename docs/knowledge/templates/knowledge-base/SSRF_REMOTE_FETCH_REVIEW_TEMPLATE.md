# SSRF Remote Fetch Review Template

Use this record for features that fetch a remote resource based on client-supplied or externally influenced URLs, including webhooks, previews, file imports, metadata retrieval, and similar capabilities.

## Review metadata

- Feature/service: `<name>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Remote-fetch client/library: `<client>`

## Fetch policy

- Allowed URL schemes: `<list>`
- Allowed destination origins/hosts: `<list or policy>`
- Allowed ports: `<list or policy>`
- Allowed media/content types: `<list or policy>`
- Redirect policy: `<disabled/revalidated policy>`
- Connection/operation deadline: `<value>`
- Maximum response size: `<value>`
- Network-layer egress restriction: `<summary>`

## Review checks

- [ ] User-supplied URL input is parsed with a maintained URL parser before connection.
- [ ] Expected schemes, destinations, ports, and content types are allowlisted where the business function permits it.
- [ ] Loopback, internal-address, link-local/metadata-service, and other disallowed destinations are blocked by policy and/or network controls.
- [ ] Automatic redirects are disabled unless explicitly required.
- [ ] When redirects are required, every redirect target is revalidated before following it.
- [ ] Arbitrary upstream response bodies, headers, and internal timing detail are not exposed to the external caller.
- [ ] Fetch time and response size are bounded.

## Test evidence

| Scenario | Expected | Actual | Evidence |
| --- | --- | --- | --- |
| Allowed public destination | `<allow>` | `<result>` | `<reference>` |
| Loopback/internal target | `<deny>` | `<result>` | `<reference>` |
| Metadata/link-local target | `<deny>` | `<result>` | `<reference>` |
| Allowed URL redirecting to blocked target | `<deny>` | `<result>` | `<reference>` |
| Oversized/slow response | `<bounded failure>` | `<result>` | `<reference>` |

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Sources

- OWASP API7:2023 Server Side Request Forgery: https://owasp.org/API-Security/editions/2023/en/0xa7-server-side-request-forgery/
- OWASP Server-Side Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
