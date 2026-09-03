# Tool Capability Allowlisting

## Purpose

Control profile for **OWASP ASI02: Tool Misuse and Exploitation**.

## Control

Expose only tools and operations required for the current task class. Model selection must not turn an otherwise unavailable capability into an authorized one.

## Validation

Request out-of-scope tools by name, alias, and chained indirection; verify they remain unavailable or denied.

## Failure correction

Remove excess registrations, narrow task-to-tool mappings, revoke cached catalogs, and retest the affected task class.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://genai.owasp.org/resource/agent-control-standard-acs/
