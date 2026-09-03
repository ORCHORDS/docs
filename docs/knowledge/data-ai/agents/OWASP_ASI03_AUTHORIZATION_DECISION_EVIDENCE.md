# Authorization Decision Evidence

## Purpose

Control profile for **OWASP ASI03: Identity and Privilege Abuse**.

## Control

Record the principal, delegated actor, requested action, resource, policy version, decision, and relevant task context for privileged authorization decisions.

## Validation

Sample allowed and denied actions and verify evidence can reconstruct why the decision occurred without logging raw secrets.

## Failure correction

Repair missing decision telemetry, preserve alternative evidence for affected events, and add coverage tests for the enforcement point.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://spiffe.io/docs/latest/spiffe-specs/spiffe_workload_api/
