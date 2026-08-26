# HTTP API problem details: stable errors without sensitive diagnostics

**Category:** Patterns
**Author:** ORCHORDS
**Primary source:** [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)

## Problem

Clients need machine-readable failure semantics, while operators need detailed diagnostics. Returning raw exception messages conflates those needs and can expose internals, credentials, or personal data.

## Pattern

- Use a documented problem type URI for each stable public error class and provide a human-readable title.
- Include an HTTP status appropriate to the response and a safe request correlation identifier for support and logs.
- Make client-actionable fields explicit and documented; do not make clients parse a free-form detail string.
- Treat the detail field as untrusted public text. Omit implementation traces, provider responses, SQL errors, secrets, and identifiers the caller is not authorized to see.
- Keep high-cardinality diagnostics in protected logs linked by the correlation identifier.
- Version or retire problem types deliberately; clients may depend on their semantics.

## Verification

1. Exercise validation, authorization, not-found, conflict, timeout, and upstream-failure paths.
2. Confirm every response has the intended content type, status, type, title, and safe correlation ID.
3. Search response bodies for stack traces, tokens, internal URLs, raw provider messages, and personal data.
4. Confirm a client can make its retry or user-action decision from documented fields rather than detail text.

## Failure modes

- Returning the same generic response for every condition prevents safe client recovery.
- Returning exception text leaks internals and creates an unstable client contract.
- A status code and a body type disagree, leading clients and monitoring to classify the error differently.

## Related

- [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html)
