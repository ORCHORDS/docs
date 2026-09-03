# Privilege Attenuation Across Delegation

## Purpose

Control profile for **OWASP ASI03: Identity and Privilege Abuse**.

## Control

Ensure delegated authority is equal to or narrower than the delegator's authority and the current task need; delegation must never amplify privileges.

## Validation

Create multi-hop delegation chains and verify each hop monotonically reduces or preserves allowed scope.

## Failure correction

Terminate the chain, revoke amplified credentials, and fix the token-exchange or policy rule that permitted escalation.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.rfc-editor.org/rfc/rfc8693
- https://www.rfc-editor.org/rfc/rfc9700
