# Inter-Agent Error Sanitization

## Purpose

Control profile for **OWASP ASI07: Insecure Inter-Agent Communication**.

## Control

Return protocol errors that support recovery without disclosing private prompts, credentials, hidden policy, or sensitive backend details to peer agents.

## Validation

Trigger authentication, schema, policy, and backend failures and inspect exact peer-visible messages.

## Failure correction

Redact the leaking field, update error mapping, purge exposed logs or messages where feasible, and rotate leaked secrets.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://a2a-protocol.org/dev/specification/
- https://genai.owasp.org/resource/agent-control-standard-acs/
