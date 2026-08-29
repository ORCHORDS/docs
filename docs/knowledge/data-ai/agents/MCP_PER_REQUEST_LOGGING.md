# MCP Per-Request Logging Controls

## Purpose

In the MCP 2026-07-28 era, logging preference moves away from session-scoped `logging/setLevel`. A request can carry a log-level preference in `_meta.logLevel`, making logging behavior explicit for that operation in a stateless protocol.

## Guidance

1. Treat an absent log-level preference as an opt-out or implementation-defined conservative default.
2. Never use client-requested verbosity to bypass server-side security or privacy restrictions.
3. Redact credentials, secrets, sensitive arguments, and personal data regardless of requested log level.
4. Keep operational audit events separate from developer-debug verbosity.
5. Apply rate and size limits to verbose logging.
6. Propagate correlation context without copying sensitive request bodies into every log record.
7. Document which levels a server supports and normalize unknown values safely.

## Sources

- MCP TypeScript SDK — supporting protocol revision 2026-07-28: https://ts.sdk.modelcontextprotocol.io/v2/migration/support-2026-07-28
- Model Context Protocol — 2026-07-28 specification release: https://blog.modelcontextprotocol.io/posts/2026-07-28/

## Scope note

Protocol logging controls influence verbosity; organizational logging, retention, privacy, and audit policy remain authoritative.
