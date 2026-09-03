# Tool Argument Policy Enforcement

## Purpose

Control profile for **OWASP ASI02: Tool Misuse and Exploitation**.

## Control

Validate tool arguments against schema and policy before execution, including resource identifiers, destinations, ranges, and high-impact flags.

## Validation

Test valid, malformed, boundary, encoded, and policy-forbidden arguments; verify rejection happens before side effects.

## Failure correction

Block the affected tool path, tighten validation at the execution boundary, and add the rejected payloads to tests.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://genai.owasp.org/resource/agent-control-standard-acs/
