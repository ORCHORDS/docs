# HTTP Problem Details Review Record Template

Use this record to review an HTTP API problem-details contract against RFC 9457. Replace placeholders with evidence; do not include secrets or production-sensitive diagnostics.

## Review metadata

- Service/API: `<name>`
- Endpoint or operation: `<operation>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Contract version: `<version>`

## Problem type contract

- Type URI: `<https://example.invalid/problems/type>`
- Title: `<short title>`
- Intended HTTP status: `<status>`
- Type documentation location: `<public or controlled documentation reference>`
- Defined extension members: `<names and semantics>`

## Client compatibility checks

- [ ] Clients use `type` or defined extension members for machine decisions.
- [ ] Clients do not parse human-readable `detail` text.
- [ ] Rewording or localization of `detail` does not alter behavior.
- [ ] Existing problem-type semantics remain backward compatible.

## Information-disclosure checks

- [ ] Response contains no stack traces or internal file paths.
- [ ] Response contains no database/query diagnostics.
- [ ] Response contains no credentials, private hostnames, or internal identifiers.
- [ ] Support correlation data is intentionally designed and safe to expose.

## Evidence

- Contract/schema reference: `<reference>`
- Representative response samples: `<reference>`
- Compatibility test result: `<result>`
- Disclosure test result: `<result>`
- Findings and corrective actions: `<text>`

## Source

- RFC 9457, Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
