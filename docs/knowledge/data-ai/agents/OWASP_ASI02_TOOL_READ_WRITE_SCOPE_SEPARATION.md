# Tool Read and Write Scope Separation

## Purpose

Control profile for **OWASP ASI02: Tool Misuse and Exploitation**.

## Control

Use distinct capabilities for reading and mutating resources so an agent authorized to inspect data does not automatically inherit modification rights.

## Validation

Exercise read-only tasks against write endpoints and mutation tasks against read-only identities; verify scopes cannot be silently upgraded.

## Failure correction

Split mixed credentials or tool methods, invalidate over-broad tokens, and reissue least-privilege access.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://genai.owasp.org/resource/agent-control-standard-acs/
