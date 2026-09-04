# Secure Query Construction Policy Review Template

Use this record to verify that database query construction prevents user-controlled values from being interpreted as SQL syntax and that the prevention mechanism is enforced consistently across a product.

## Review metadata

- Product/service scope: `<scope>`
- Data-access technologies/ORMs: `<technologies>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Secure coding standard/reference: `<reference>`

## Query-path inventory

| Query/data-access path | User-controlled data possible? | Parameterized/bound values? | Dynamic identifier handling | Raw-query escape hatch? | Enforcement/test evidence |
| --- | --- | --- | --- | --- | --- |
| `<path>` | `<yes/no>` | `<yes/no/n-a>` | `<allowlist/design>` | `<yes/no + governance>` | `<reference>` |

## Policy checks

- [ ] User-controlled values are passed through parameterized/bound query mechanisms rather than concatenated into SQL text.
- [ ] The engineering standard prohibits ad-hoc query-string construction with untrusted input.
- [ ] ORM/query-builder escape hatches and raw-query APIs are identified and governed rather than assumed safe because an ORM is present.
- [ ] Dynamic table/column/order identifiers use explicit allowlists or another non-value parameter mechanism appropriate to the database/API.
- [ ] Shared data-access helpers make the secure path easier/default and reduce repeated hand-built query construction.
- [ ] Code review and automated analysis include checks for unsafe query-construction patterns.
- [ ] Legacy query paths have owners and remediation/migration milestones.
- [ ] A prior SQL-injection finding triggers class-wide review rather than only a local patch.

## Verification exercise

- Representative input-to-query paths tested: `<references>`
- Raw-query/static analysis search: `<reference/result>`
- Negative/adversarial input tests: `<reference/result>`
- Legacy exceptions found: `<reference>`
- Remediation/retest result: `<result>`

## Findings and actions

- Unsafe construction paths: `<text>`
- Missing enforcement/tooling: `<text>`
- Corrective actions/owner/date: `<text>`

## Source

- NSA/CISA, Top Ten Cybersecurity Misconfigurations — use parameterized queries and secure coding practices: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-278a
