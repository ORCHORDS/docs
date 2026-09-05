# Human Override Auditing

## Purpose

Control profile for **OWASP ASI09: Human-Agent Trust Exploitation**.

## Control

Record when humans override agent recommendations or policy warnings, including the action, reason, reviewer identity, and resulting outcome.

## Validation

Exercise approve, deny, modify, and override paths and verify evidence distinguishes each decision without storing unnecessary personal data.

## Failure correction

Repair missing audit events, review risky overrides, and add monitoring for repeated override patterns.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
