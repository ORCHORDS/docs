# MCP Tool Name Governance

## Purpose

MCP tool names are protocol identifiers used for discovery and invocation. The 2025-11-25 specification added explicit guidance for tool names so servers and clients can avoid portability problems caused by ambiguous characters, unstable casing, or duplicate identifiers.

## Current naming guidance

For MCP tools, the current specification says names SHOULD:

- be between 1 and 128 characters inclusive;
- be treated as case-sensitive;
- use only ASCII letters, digits, underscore (`_`), hyphen (`-`), and dot (`.`);
- avoid spaces, commas, and other special characters; and
- be unique within the server.

Examples of valid names in the specification include `getUser`, `DATA_EXPORT_v2`, and `admin.tools.list`.

## Governance pattern

1. Define a stable naming convention before publishing a tool surface.
2. Treat name changes as compatibility changes because clients and prompts may persist tool identifiers.
3. Reject duplicate names during server initialization or tool registration.
4. Preserve case exactly when routing calls; do not silently normalize names unless the client explicitly documents that behavior.
5. Keep human-facing wording in `title` or descriptions rather than embedding spaces or display punctuation in the protocol identifier.
6. Validate names before advertising them through `tools/list`.
7. When federating multiple MCP servers into one model tool namespace, detect collisions after any client-side prefixing or sanitization.

## Display names versus identifiers

MCP separates the programmatic `name` from optional human-readable title information. Interfaces should use the human-facing title where appropriate without assuming the title is safe or stable as an invocation identifier.

## Security considerations

Tool names alone do not establish trust or authorization. A familiar or privileged-looking name must not grant broader permissions. Clients should continue to apply server trust, user approval, schema validation, and least-privilege authorization independently of the tool's name.

## Failure modes

- Case folding can route `deleteUser` and `DeleteUser` incorrectly.
- Silent character replacement can cause two distinct server tools to collapse to one client-visible name.
- Reusing a tool name for materially different behavior can invalidate cached permissions or model assumptions.
- Using display strings as protocol identifiers creates avoidable portability problems.

## Sources

- Model Context Protocol — Tools, revision 2025-11-25: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- Model Context Protocol — 2025-11-25 changelog: https://modelcontextprotocol.io/specification/2025-11-25/changelog
- Model Context Protocol — Schema reference: https://modelcontextprotocol.io/specification/2025-11-25/schema

## Scope note

The MCP specification expresses most tool-name rules as SHOULD-level interoperability guidance rather than an authorization control. Client products may apply additional naming or sanitization rules and should document them separately.