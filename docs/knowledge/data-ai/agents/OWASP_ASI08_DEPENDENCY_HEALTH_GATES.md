# Dependency Health Gates

## Purpose

Control profile for **OWASP ASI08: Cascading Failures**.

## Control

Gate new agent work on critical dependency health when continued execution would amplify damage, stale data, or repeated failure.

## Validation

Mark a dependency unhealthy and verify high-risk tasks stop while explicitly safe degraded operations remain available if designed.

## Failure correction

Open the gate only after health criteria recover, clear stale state, and investigate tasks admitted during the unhealthy period.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
- https://genai.owasp.org/resource/agent-control-standard-acs/
