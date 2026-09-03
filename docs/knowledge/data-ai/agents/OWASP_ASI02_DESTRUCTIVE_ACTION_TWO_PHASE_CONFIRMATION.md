# Destructive Action Two-Phase Confirmation

## Purpose

Control profile for **OWASP ASI02: Tool Misuse and Exploitation**.

## Control

Separate preparation from commit for destructive or irreversible operations. First produce an exact action preview; commit only after an independent confirmation condition.

## Validation

Attempt deletion, overwrite, revocation, or mass change without the commit phase and verify no destructive side effect occurs.

## Failure correction

Abort the operation, restore from available recovery points, and move confirmation enforcement into the tool or service boundary.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
