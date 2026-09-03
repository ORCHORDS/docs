# Inter-Agent Trace Context Integrity

## Purpose

Control profile for **OWASP ASI07: Insecure Inter-Agent Communication**.

## Control

Treat trace and correlation identifiers as diagnostic context, not proof of identity or authorization, and protect them from unsafe use in security decisions.

## Validation

Forge or reuse trace identifiers from another task and verify authorization remains based on authenticated security context.

## Failure correction

Correct the code path that trusted trace data, rotate related session material if needed, and add spoofed trace cases to tests.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://a2a-protocol.org/dev/specification/
- https://genai.owasp.org/resource/agent-control-standard-acs/
