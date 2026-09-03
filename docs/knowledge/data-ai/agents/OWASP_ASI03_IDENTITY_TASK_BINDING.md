# Identity-to-Task Binding

## Purpose

Control profile for **OWASP ASI03: Identity and Privilege Abuse**.

## Control

Bind privileged sessions or delegated authority to a specific task, workflow, or approval context where infrastructure supports it.

## Validation

Reuse authority from a completed or unrelated task and verify policy treats the detached context as invalid.

## Failure correction

Revoke stale sessions, narrow binding metadata and lifetime, and audit executions that reused detached authority.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.rfc-editor.org/rfc/rfc8693
- https://www.rfc-editor.org/rfc/rfc8707
