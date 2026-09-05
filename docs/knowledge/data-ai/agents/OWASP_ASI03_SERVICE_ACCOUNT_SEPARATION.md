# Agent Service Account Separation

## Purpose

Control profile for **OWASP ASI03: Identity and Privilege Abuse**.

## Control

Separate service identities by environment and responsibility so development, testing, administration, and production agents cannot share a single trust principal.

## Validation

Attempt cross-environment and cross-role access with each identity; verify authorization reflects the intended boundary.

## Failure correction

Split the shared account, reassign resource policies, rotate credentials, and review historical access made under the ambiguous identity.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/
- https://www.rfc-editor.org/rfc/rfc9700
