# Short-Lived Agent Credentials

## Purpose

Control profile for **OWASP ASI03: Identity and Privilege Abuse**.

## Control

Prefer short-lived credentials obtained at runtime over long-lived embedded secrets so compromise duration is bounded and rotation is routine.

## Validation

Expire or revoke a credential during a long task and verify the agent reacquires authority through the approved path rather than bypassing checks.

## Failure correction

Revoke the exposed credential, shorten lifetime or refresh scope, and remove any fallback that restores static secrets.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/
- https://www.rfc-editor.org/rfc/rfc9700
