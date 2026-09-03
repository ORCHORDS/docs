# Context Conflict Resolution

## Purpose

Control profile for **OWASP ASI06: Memory and Context Poisoning**.

## Control

Define how conflicting memory, retrieval, policy, and fresh user input are resolved instead of letting arbitrary recency or model preference choose authority.

## Validation

Provide contradictory values from sources with different trust and freshness; verify resolution follows documented rules.

## Failure correction

Remove the wrongly preferred context, correct precedence logic, and add the conflict case to regression tests.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
