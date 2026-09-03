# Agent Credential Rotation

## Purpose

Control profile for **OWASP ASI03: Identity and Privilege Abuse**.

## Control

Rotate agent credentials and trust material on a defined cadence and on compromise, ownership change, or policy change without requiring model cooperation.

## Validation

Rotate active credentials while tasks are running and verify old material stops working after the intended overlap window.

## Failure correction

Revoke outdated material, repair consumers that bypass current trust bundles, and document rotation evidence.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/
- https://www.rfc-editor.org/rfc/rfc9700
