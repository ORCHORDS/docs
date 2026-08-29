# A2A Standardized Error Handling

## Purpose

A2A v1.0 standardizes error responses around `google.rpc.Status` and `google.rpc.ErrorInfo`. HTTP+JSON and JSON-RPC bindings use structured error details so clients can reason about protocol-specific failures without depending only on human-readable messages.

## Guidance

1. Map failures to the protocol's defined status/error taxonomy instead of inventing local string formats.
2. Include A2A-specific `ErrorInfo` with a stable `reason` and the `a2a-protocol.org` domain where required.
3. Keep human-readable error messages useful but do not make client behavior depend on their exact wording.
4. Do not expose stack traces, credentials, internal hostnames, or sensitive data in error metadata.
5. Preserve a correlation identifier outside sensitive error details for troubleshooting.
6. Distinguish retryable transport/service failures from permanent request or authorization errors.
7. Test equivalent error semantics across the protocol bindings an agent advertises.

## Sources

- A2A Protocol — What's New in v1.0: https://a2a-protocol.org/latest/whats-new-v1/
- A2A Protocol — current specification error handling: https://a2a-protocol.org/dev/specification/

## Scope note

Structured errors improve interoperability. Application-specific recovery policy still needs to decide whether a particular error should be retried, escalated, or surfaced to a user.
