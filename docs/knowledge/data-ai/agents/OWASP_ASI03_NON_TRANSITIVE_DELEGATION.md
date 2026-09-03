# Non-Transitive Delegation by Default

## Purpose

Control profile for **OWASP ASI03: Identity and Privilege Abuse**.

## Control

Do not let a receiving agent further delegate authority unless that capability is explicitly granted and policy-bounded.

## Validation

Delegate to a peer and attempt a second delegation to another peer; verify the second hop is denied unless expressly authorized.

## Failure correction

Revoke the transitive credential, disable delegation rights for the intermediary, and review downstream actions from the unauthorized chain.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.rfc-editor.org/rfc/rfc8693
- https://www.rfc-editor.org/rfc/rfc9700
