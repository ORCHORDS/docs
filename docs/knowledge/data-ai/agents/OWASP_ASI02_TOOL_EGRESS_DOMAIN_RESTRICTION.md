# Tool Egress Domain Restriction

## Purpose

Control profile for **OWASP ASI02: Tool Misuse and Exploitation**.

## Control

Restrict network-capable tools to approved destinations, protocols, and purpose-specific endpoints instead of allowing arbitrary model-chosen egress.

## Validation

Try direct, redirected, encoded, and alternate-port destinations outside the approved set; verify the runtime blocks them.

## Failure correction

Revoke broad network permissions, inspect any successful egress, rotate exposed credentials if needed, and update destination policy.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://genai.owasp.org/resource/agent-control-standard-acs/
