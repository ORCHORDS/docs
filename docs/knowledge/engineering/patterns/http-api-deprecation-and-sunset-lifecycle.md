# HTTP API deprecation and sunset lifecycle

**Category:** Patterns
**Author:** ORCHORDS
**Primary source:** [RFC 9745: Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html)

## Problem

Removing or changing an API endpoint without a discoverable transition path breaks clients that were never notified. Documentation alone is not enough when clients depend on a resource at runtime.

## Pattern

- Maintain an owner, replacement path, compatibility assessment, planned deprecation date, and removal date for every retiring resource.
- Emit the HTTP Deprecation response header on the specific resource once a deprecation decision is public.
- Provide a Link header with relation deprecation that points to an HTTPS migration guide with replacement, examples, support contact, and timeline.
- Use the Sunset header only when the resource is expected to become unresponsive; its date must not precede deprecation.
- Measure active usage by client identity or version before and during the transition, and contact high-impact consumers through agreed channels.
- Treat these headers as hints: preserve a tested communication and support plan rather than assuming every client consumes them.

## Verification

1. Fetch a deprecated endpoint and validate the header dates and documentation link.
2. Test the replacement with representative clients before announcing deprecation.
3. Confirm dashboards identify remaining client usage without collecting unnecessary personal data.
4. Rehearse the sunset response and rollback path before the removal date.

## Failure modes

- A deprecation date is announced without a usable replacement or migration guide.
- A global header is assumed to apply to all endpoints, while consumers only see a resource-specific hint.
- Sunset occurs before clients have a support path or measured migration window.

## Related

- [RFC 9745](https://www.rfc-editor.org/rfc/rfc9745.html)
